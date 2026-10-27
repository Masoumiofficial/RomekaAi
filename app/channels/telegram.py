"""Telegram channel — real webhook verification + allowlist identity mapping.

LIVE STATUS: HTTP call shapes follow the public Bot API, but no bot token or
live Telegram endpoint was available in this workspace, so end-to-end delivery
is NOT verified. Webhook parsing, secret verification, allowlisting and command
routing ARE covered by tests (tests/test_channels.py) with mocked HTTP.
"""
from __future__ import annotations

import logging

import httpx
from sqlalchemy.orm import Session

from app.agents.orchestrator import CoreOrchestrator, log_security_event
from app.channels.base import ChannelAdapter, ChannelResult
from app.config import Settings, get_settings
from app.core.security import constant_time_equal
from app.db.models import ChannelIdentity, Plan, Task, User
from app.core.timeutil import today_in

log = logging.getLogger("romka.channels.telegram")


class TelegramAdapter(ChannelAdapter):
    name = "telegram"

    def __init__(self, settings: Settings | None = None, client: httpx.Client | None = None) -> None:
        self.settings = settings or get_settings()
        self._client = client

    @property
    def available(self) -> bool:
        return bool(self.settings.TELEGRAM_BOT_TOKEN)

    @property
    def base_url(self) -> str:
        return f"https://api.telegram.org/bot{self.settings.TELEGRAM_BOT_TOKEN}"

    def verify(self, headers: dict) -> bool:
        expected = self.settings.TELEGRAM_WEBHOOK_SECRET
        if not expected:
            return False
        got = headers.get("x-telegram-bot-api-secret-token", "")
        return bool(got) and constant_time_equal(got, expected)

    def resolve_user(self, db: Session, external_id: str) -> int | None:
        row = (db.query(ChannelIdentity)
               .filter(ChannelIdentity.channel == self.name,
                       ChannelIdentity.external_id == str(external_id),
                       ChannelIdentity.is_allowed.is_(True)).first())
        if row:
            return row.user_id
        # Also honour the static env allowlist for first-boot bootstrap.
        allowed = [x.strip() for x in self.settings.TELEGRAM_ALLOWED_USER_IDS.split(",") if x.strip()]
        if str(external_id) in allowed:
            return None  # authenticated but not yet mapped to a ROMKA user
        return None

    def _deny(self, db: Session, external_id: str, detail: str) -> None:
        log_security_event(db, event_type="unauthorized_channel_access",
                           channel=self.name, detail=detail, ip=str(external_id))
        log.warning("denied telegram request from %s", external_id)

    def handle_update(self, db: Session, payload: dict) -> ChannelResult:
        msg = payload.get("message") or payload.get("edited_message") or {}
        sender = (msg.get("from") or {})
        external_id = str(sender.get("id", ""))
        chat_id = (msg.get("chat") or {}).get("id")
        text = (msg.get("text") or "").strip()

        # Secret-header verification happens at the HTTP endpoint (see
        # app/api/channels.py). This method assumes the caller verified it.
        if not external_id:
            self._deny(db, "unknown", "missing sender id")
            return ChannelResult(False, "درخواست نامعتبر است.")

        user_id = self.resolve_user(db, external_id)
        if user_id is None:
            self._deny(db, external_id, "sender not in channel allowlist")
            return ChannelResult(False, "دسترسی مجاز نیست. این رخداد ثبت شد.")

        core = CoreOrchestrator(db, user_id=user_id, settings=self.settings)
        if text.startswith("/"):
            command, _, rest = text.partition(" ")
            command = command.split("@")[0].lower()
            return self._command(db, core, command, rest.strip(), chat_id, user_id)
        try:
            out = core.handle(text)
            return ChannelResult(True, out["answer"], data={"conversation_id": out["conversation_id"]})
        except Exception as exc:
            log.exception("telegram core failure")
            return ChannelResult(False, f"خطا در پردازش: {type(exc).__name__}")

    def _command(self, db: Session, core: CoreOrchestrator, command: str, rest: str,
                 chat_id: int | None, user_id: int) -> ChannelResult:
        if command in ("/start", "/help"):
            return ChannelResult(True,
                "رومکا — دستورها:\n/today برنامه امروز\n/task <عنوان> ثبت وظیفه\n"
                "/remember <متن> ثبت در حافظه\n/ask <پرسش> گفتوگو\n/status وضعیت",
                buttons=[[{"text": "برنامه امروز", "callback_data": "today"}]])
        if command == "/today":
            plan = (db.query(Plan).filter(Plan.user_id == user_id, Plan.is_active.is_(True))
                    .order_by(Plan.date.desc()).first())
            if not plan:
                return ChannelResult(True, "برنامهای ثبت نشده. ابتدا /plan را بزن.")
            lines = [f"{b['start']}–{b['end']} {b['title']}" for b in plan.payload.get("blocks", [])]
            return ChannelResult(True, "برنامه امروز:\n" + "\n".join(lines))
        if command == "/plan":
            from app.db.models import UserProfile
            from app.planning.service import generate
            user = db.query(User).filter(User.id == user_id).first()
            tz_name = user.timezone if user else "UTC"
            profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
            result = generate(db, user_id=user_id, day=today_in(tz_name), profile=profile,
                              tz_name=tz_name)
            return ChannelResult(True, f"برنامه ساخته شد. {len(result['scheduled'])} کار، "
                                       f"{result['metrics']['utilization_pct']}٪ اشغال.\n" +
                                       "\n".join(result["warnings"][:3]))
        if command == "/task" and rest:
            db.add(Task(user_id=user_id, title=rest[:300], duration_min=60, priority=3))
            db.flush()
            return ChannelResult(True, f"وظیفه «{rest[:80]}» ثبت شد.")
        if command == "/remember" and rest:
            core.handle(f"به خاطر بسپار {rest[:250]}")
            return ChannelResult(True, "در حافظه ثبت شد.")
        if command == "/ask" and rest:
            return ChannelResult(True, core.handle(rest)["answer"])
        if command == "/status":
            tasks = db.query(Task).filter(Task.user_id == user_id, Task.status != "done").count()
            return ChannelResult(True, f"وظایف باز: {tasks}")
        return ChannelResult(True, "دستور ناشناخته. /help را ببین.")

    def send_message(self, chat_id: int, text: str) -> bool:
        """Real outbound call. Requires a live token; failures are contained."""
        if not self.available:
            return False
        try:
            client = self._client or httpx
            resp = client.post(f"{self.base_url}/sendMessage",
                               json={"chat_id": chat_id, "text": text[:4000]}, timeout=10.0)
            return resp.status_code == 200
        except httpx.HTTPError as exc:
            log.warning("telegram send failed: %s", type(exc).__name__)
            return False

"""Bale channel — verified official API shape, live delivery NOT yet verified.

Verified on 2026-10-27 against the official documentation at
https://docs.bale.ai/ : the Bale Bot API is Telegram-compatible and requests go
to `https://tapi.bale.ai/bot<token>/METHOD_NAME` (getUpdates / setWebhook /
sendMessage). Webhook ports supported by Bale are 443 and 88.

LIMITATION: no Bale bot token or reachable live endpoint was available here, so
`send_message` and webhook delivery are implemented but NOT end-to-end tested.
Unlike Telegram, setWebhook docs do not expose a secret-header parameter, so we
enforce our own shared secret as a `?secret=` query parameter on the webhook URL.
The channel never defines identity by itself: external_id must be mapped to a
ROMKA user through `channel_identities` (see Scenario F).
"""
from __future__ import annotations

import logging

import httpx
from sqlalchemy.orm import Session

from app.agents.orchestrator import CoreOrchestrator, log_security_event
from app.channels.base import ChannelAdapter, ChannelResult
from app.channels.telegram import TelegramAdapter
from app.config import Settings, get_settings
from app.core.security import constant_time_equal
from app.db.models import ChannelIdentity

log = logging.getLogger("romka.channels.bale")


class BaleAdapter(ChannelAdapter):
    name = "bale"

    def __init__(self, settings: Settings | None = None, client: httpx.Client | None = None) -> None:
        self.settings = settings or get_settings()
        self._client = client
        # Business logic is reused through a Telegram-shaped handler; only the
        # transport, identity namespace and verification differ.
        self._logic = TelegramAdapter(settings=self.settings, client=client)

    @property
    def available(self) -> bool:
        return bool(self.settings.BALE_BOT_TOKEN and self.settings.BALE_WEBHOOK_SECRET)

    @property
    def base_url(self) -> str:
        return f"{self.settings.BALE_API_BASE_URL.rstrip('/')}/bot{self.settings.BALE_BOT_TOKEN}"

    def verify(self, headers: dict) -> bool:
        """`headers` here carries the parsed query params from the webhook URL."""
        expected = self.settings.BALE_WEBHOOK_SECRET
        got = headers.get("secret", "")
        return bool(expected and got) and constant_time_equal(got, expected)

    def resolve_user(self, db: Session, external_id: str) -> int | None:
        row = (db.query(ChannelIdentity)
               .filter(ChannelIdentity.channel == self.name,
                       ChannelIdentity.external_id == str(external_id),
                       ChannelIdentity.is_allowed.is_(True)).first())
        return row.user_id if row else None

    def handle_update(self, db: Session, payload: dict) -> ChannelResult:
        msg = payload.get("message") or payload.get("edited_message") or {}
        external_id = str((msg.get("from") or {}).get("id", ""))
        if not external_id:
            log_security_event(db, event_type="unauthorized_channel_access",
                               channel=self.name, detail="missing sender id")
            return ChannelResult(False, "درخواست نامعتبر است.")
        user_id = self.resolve_user(db, external_id)
        if user_id is None:
            log_security_event(db, event_type="unauthorized_channel_access",
                               channel=self.name, detail="sender not mapped/allowed",
                               ip=external_id)
            return ChannelResult(False, "دسترسی مجاز نیست. این رخداد ثبت شد.")
        text = (msg.get("text") or "").strip()
        if not text:
            return ChannelResult(True, "پیامی دریافت نشد.")
        try:
            out = CoreOrchestrator(db, user_id=user_id, settings=self.settings).handle(text)
            return ChannelResult(True, out["answer"],
                                 data={"conversation_id": out["conversation_id"]})
        except Exception as exc:
            log.exception("bale core failure")
            return ChannelResult(False, f"خطا در پردازش: {type(exc).__name__}")

    def send_message(self, chat_id: int, text: str) -> bool:
        if not self.available:
            return False
        try:
            client = self._client or httpx
            resp = client.post(f"{self.base_url}/sendMessage",
                               json={"chat_id": chat_id, "text": text[:4000]}, timeout=10.0)
            return resp.status_code == 200
        except httpx.HTTPError as exc:
            log.warning("bale send failed: %s", type(exc).__name__)
            return False

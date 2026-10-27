"""Action Engine: decisions are separated from execution.

An AI agent never gets execution rights from generated text. Tools are registered
in code (not in config), inputs are validated, risky actions require explicit
user approval, and idempotency keys make safe retries possible.
"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from sqlalchemy.orm import Session

from app.core.errors import PermissionDenied, ValidationFailed
from app.db.models import ActionRecord

log = logging.getLogger("romka.actions")

RISK_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}


@dataclass(frozen=True)
class ToolSpec:
    name: str
    risk: str
    handler: Callable[..., dict]
    input_schema: dict  # minimal JSON-schema-ish: {param: type_name}
    description: str = ""


class ActionEngine:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        if spec.name in self._tools:
            raise ValueError(f"duplicate tool: {spec.name}")
        if spec.risk not in RISK_ORDER:
            raise ValueError(f"bad risk level: {spec.risk}")
        self._tools[spec.name] = spec

    @property
    def tools(self) -> dict[str, ToolSpec]:
        return dict(self._tools)

    def allowed_tools(self, allowlist: list[str]) -> list[str]:
        """Config may only NARROW the code-defined tool set, never widen it."""
        return [name for name in allowlist if name in self._tools]

    def _validate(self, spec: ToolSpec, inputs: dict) -> None:
        for key, expected in spec.input_schema.items():
            if key not in inputs:
                raise ValidationFailed(f"پارامتر «{key}» برای ابزار {spec.name} لازم است.")
            value = inputs[key]
            types = {
                "str": str, "int": int, "float": (int, float), "bool": bool,
                "list": list, "dict": dict, "any": object,
            }
            py_type = types.get(expected, object)
            if expected == "int" and isinstance(value, bool):
                raise ValidationFailed(f"پارامتر «{key}» باید عدد باشد.")
            if not isinstance(value, py_type):
                raise ValidationFailed(f"نوع پارامتر «{key}» نامعتبر است.")

    def request(
        self,
        db: Session,
        *,
        user_id: int,
        requester: str,
        goal: str,
        tool: str,
        inputs: dict,
        allowlist: list[str] | None = None,
        approved: bool = False,
        idempotency_key: str | None = None,
    ) -> ActionRecord:
        spec = self._tools.get(tool)
        if spec is None:
            raise PermissionDenied(f"ابزار «{tool}» تعریف نشده است.", details={"tool": tool})
        if allowlist is not None and tool not in self.allowed_tools(allowlist):
            raise PermissionDenied(
                f"ابزار «{tool}» در فهرست مجاز «{requester}» نیست.", details={"tool": tool}
            )
        self._validate(spec, inputs)
        key = idempotency_key or hashlib.sha256(
            json.dumps([user_id, requester, tool, inputs], sort_keys=True, default=str, ensure_ascii=False).encode()
        ).hexdigest()
        existing = (
            db.query(ActionRecord)
            .filter(ActionRecord.idempotency_key == key, ActionRecord.status == "executed")
            .first()
        )
        if existing:
            return existing

        needs_approval = RISK_ORDER[spec.risk] >= RISK_ORDER["high"]
        record = ActionRecord(
            user_id=user_id, requester=requester, goal=goal, tool=tool, inputs=inputs,
            risk_level=spec.risk,
            status="pending_approval" if needs_approval and not approved else "approved",
            idempotency_key=key,
        )
        db.add(record)
        db.flush()
        if record.status == "pending_approval":
            log.info("action %s requires explicit approval (risk=%s)", record.id, spec.risk)
            return record
        return self.execute(db, record, approved=approved)

    def execute(self, db: Session, record: ActionRecord, *, approved: bool = False) -> ActionRecord:
        spec = self._tools.get(record.tool)
        if spec is None:
            record.status = "failed"
            record.error = "tool unregistered"
            db.flush()
            return record
        if RISK_ORDER[record.risk_level] >= RISK_ORDER["high"] and not approved:
            raise PermissionDenied("این اقدام نیازمند تأیید صریح کاربر است.")
        try:
            record.result = spec.handler(**record.inputs) or {}
            record.status = "executed"
            record.executed_at = datetime.now(timezone.utc)
        except Exception as exc:  # errors are data, not crashes
            record.status = "failed"
            record.error = f"{type(exc).__name__}: {exc}"[:1000]
            log.warning("action %s failed: %s", record.id, record.error)
        db.flush()
        return record


action_engine = ActionEngine()


# ── Safe built-in tools. No shell, no filesystem writes, no arbitrary network. ──
action_engine.register(
    ToolSpec(
        name="memory.write_preference",
        risk="low",
        description="Store a user preference in the memory engine.",
        input_schema={"key": "str", "value": "str"},
        handler=lambda key, value: {"stored": True, "key": key, "value": value},
    )
)
action_engine.register(
    ToolSpec(
        name="planner.preview",
        risk="low",
        description="Compute a read-only plan preview; never mutates the plan.",
        input_schema={"date": "str", "energy_mode": "str"},
        handler=lambda date, energy_mode: {"preview": True, "date": date, "energy_mode": energy_mode},
    )
)
action_engine.register(
    ToolSpec(
        name="data.export",
        risk="high",
        description="Export all personal data (requires explicit approval).",
        input_schema={"user_id": "int"},
        handler=lambda user_id: {"export_requested_for": user_id},
    )
)

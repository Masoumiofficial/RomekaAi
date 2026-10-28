"""Process-local record of the last SUCCESSFUL live provider call.

Deliberately in memory: a restart must never inherit a stale "verified live"
claim. Nothing here is persisted, and no credential is ever stored.
"""
from __future__ import annotations

import threading
from datetime import datetime, timezone

_lock = threading.Lock()
_state: dict = {"verified_live": False, "provider": "", "model": "",
                "latency_ms": 0, "verified_at": ""}


def mark_verified(provider: str, model: str, latency_ms: int) -> None:
    with _lock:
        _state.update(verified_live=True, provider=provider, model=model,
                      latency_ms=latency_ms,
                      verified_at=datetime.now(timezone.utc).isoformat())


def reset_verification() -> None:
    with _lock:
        _state.update(verified_live=False, provider="", model="",
                      latency_ms=0, verified_at="")


def verification_state() -> dict:
    with _lock:
        return dict(_state)

"""Structured logging with secret redaction. Never log credentials or user content by default."""
from __future__ import annotations

import json
import logging
import re
import sys
from typing import Any

_REDACT = re.compile(
    r"(?i)\b(api[_-]?key|token|secret|password|authorization|cookie|bearer)(\s*[=:]\s*)(\S+)"
)


def redact(value: Any) -> str:
    text = value if isinstance(value, str) else str(value)
    return _REDACT.sub(lambda m: f"{m.group(1)}{m.group(2)}***REDACTED***", text)


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            record.msg = redact(record.getMessage())
            record.args = ()
        except Exception:
            record.msg = "(log record could not be formatted)"
            record.args = ()
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(RedactingFilter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)


def audit(logger: logging.Logger, event: str, **fields: Any) -> None:
    """Security-relevant event. Values are redacted; never pass raw secrets."""
    logger.info("AUDIT %s %s", event, json.dumps({k: redact(v) for k, v in fields.items()}, ensure_ascii=False))

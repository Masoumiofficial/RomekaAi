"""Authentication primitives — no third-party auth framework needed at this scale.

- Passwords: PBKDF2-HMAC-SHA256, 260k iterations, per-user random salt.
- Sessions: signed, timestamped cookies (itsdangerous), HttpOnly + SameSite=Lax.
- CSRF: double-submit token embedded in the session, echoed in a header.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

_PBKDF2_ROUNDS = 260_000


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ROUNDS)
    return f"pbkdf2_sha256${_PBKDF2_ROUNDS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, rounds, salt_hex, digest_hex = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(rounds)
        )
        return hmac.compare_digest(digest.hex(), digest_hex)
    except (ValueError, TypeError):
        return False


@dataclass(frozen=True)
class SessionData:
    user_id: int
    csrf: str


class SessionSigner:
    def __init__(self, secret_key: str, max_age: int) -> None:
        self._serializer = URLSafeTimedSerializer(secret_key, salt="romka-session-v1")
        self._max_age = max_age

    def create(self, user_id: int, csrf_token: str) -> str:
        return self._serializer.dumps({"uid": user_id, "csrf": csrf_token})

    def read(self, token: str) -> SessionData | None:
        try:
            data = self._serializer.loads(token, max_age=self._max_age)
        except (BadSignature, SignatureExpired, ValueError, TypeError):
            return None
        uid, csrf = data.get("uid"), data.get("csrf")
        if not isinstance(uid, int) or not isinstance(csrf, str):
            return None
        return SessionData(uid, csrf)


def new_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def constant_time_equal(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))

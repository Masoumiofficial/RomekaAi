"""Single source of truth for runtime configuration.

Rules (see docs/SECURITY.md): secrets come from the environment only, are never
logged, and are never stored in the repository.
"""
from __future__ import annotations

import secrets
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEV_SECRET_FILE = Path(".romka_dev_secret")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", case_sensitive=False
    )

    APP_NAME: str = "ROMKA"
    ENVIRONMENT: str = Field(default="development", pattern="^(development|testing|production)$")
    SECRET_KEY: str = ""
    DATABASE_URL: str = "sqlite:///./romka.db"
    COOKIE_SECURE: bool = False
    # auto = SameSite=None; Secure; Partitioned on HTTPS (embedded preview),
    #        SameSite=Lax on plain HTTP (local dev). Override with lax/strict/none.
    COOKIE_SAMESITE: str = "auto"
    SESSION_MAX_AGE_SECONDS: int = 604800
    RATE_LIMIT_PER_MINUTE: int = 90

    # AI provider layer
    AI_PRIMARY_PROVIDER: str = "local"       # local | openai_compatible | gapgpt
    AI_PRIMARY_BASE_URL: str = ""
    AI_PRIMARY_API_KEY: str = ""
    AI_PRIMARY_MODEL: str = "romka-local-v1"
    AI_FALLBACK_PROVIDER: str = ""
    AI_FALLBACK_BASE_URL: str = ""
    AI_FALLBACK_API_KEY: str = ""
    AI_FALLBACK_MODEL: str = ""
    AI_ALLOW_FALLBACK: bool = False
    # GapGPT preset — docs verified 2026-10-28:
    # https://gapgpt.app/platform-v2/docs/quickstart  (OpenAI-compatible /v1)
    GAPGPT_BASE_URL: str = "https://api.gapgpt.app/v1"
    GAPGPT_DEFAULT_MODEL: str = "gpt-4o-mini"
    # GapGPT prices are in IRR; operators must set their own USD estimate for
    # accurate budget caps. 0 = use the built-in conservative price table.
    AI_PRIMARY_PRICE_PER_MILLION_USD: float = 0.0
    AI_FALLBACK_PRICE_PER_MILLION_USD: float = 0.0
    AI_DAILY_BUDGET_USD: float = 1.0
    AI_MONTHLY_BUDGET_USD: float = 20.0
    AI_MAX_RETRIES: int = 1
    AI_TIMEOUT_SECONDS: float = 30.0
    AI_MAX_CALLS_PER_REQUEST: int = 3
    AI_MAX_AGENT_STEPS: int = 6
    AI_ALLOW_SENSITIVE_TO_EXTERNAL: bool = False

    # Channels
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_WEBHOOK_SECRET: str = ""
    TELEGRAM_ALLOWED_USER_IDS: str = ""
    BALE_BOT_TOKEN: str = ""
    BALE_WEBHOOK_SECRET: str = ""
    BALE_API_BASE_URL: str = "https://tapi.bale.ai"

    # Dev-only demo account. Disabled in production by ROMKA_AUTO_DEMO=false.
    ROMKA_AUTO_DEMO: bool = True
    ROMKA_DEMO_EMAIL: str = "demo@romka.local"
    ROMKA_DEMO_PASSWORD: str = "RomkaDemo2026!"
    ROMKA_DEMO_SEED_DATA: bool = True

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"

    @property
    def secret_key(self) -> str:
        """Production requires an explicit secret. Development persists a local one."""
        if self.SECRET_KEY:
            return self.SECRET_KEY
        if self.is_production:
            raise RuntimeError(
                "SECRET_KEY must be set in production. Refusing to start with an ephemeral key."
            )
        if _DEV_SECRET_FILE.exists():
            return _DEV_SECRET_FILE.read_text(encoding="utf-8").strip()
        key = secrets.token_urlsafe(48)
        _DEV_SECRET_FILE.write_text(key, encoding="utf-8")
        try:
            _DEV_SECRET_FILE.chmod(0o600)
        except OSError:
            pass
        return key

    def runtime_warnings(self) -> list[str]:
        """Honest, human-readable list of what is NOT yet production-ready."""
        out: list[str] = []
        if not self.is_production:
            out.append("ENVIRONMENT is not 'production'.")
        if self.COOKIE_SECURE is False and self.is_production:
            out.append("COOKIE_SECURE is false — sessions can travel over plain HTTP.")
        if self.DATABASE_URL.startswith("sqlite") and self.is_production:
            out.append("SQLite in production — use PostgreSQL for concurrency and backups.")
        if self.AI_PRIMARY_PROVIDER == "local":
            out.append("AI provider is the offline deterministic engine (not a hosted LLM).")
        elif not self.AI_PRIMARY_API_KEY:
            out.append(f"{self.AI_PRIMARY_PROVIDER} selected but AI_PRIMARY_API_KEY is empty — offline local engine is active.")
        else:
            out.append("External provider has a key but is NOT live-verified in this process (POST /api/v1/providers/verify).")
        if self.ROMKA_AUTO_DEMO and not self.is_production and self.ENVIRONMENT != "testing":
            out.append(f"DEV demo account is active ({self.ROMKA_DEMO_EMAIL}) — never expose this instance publicly.")
        if not self.TELEGRAM_BOT_TOKEN:
            out.append("Telegram channel disabled (no token configured).")
        if not self.BALE_BOT_TOKEN:
            out.append("Bale channel disabled (no verified token/API access).")
        if not self.SECRET_KEY and not self.is_production:
            out.append("Using local dev secret file (.romka_dev_secret, gitignored).")
        return out


@lru_cache
def get_settings() -> Settings:
    return Settings()

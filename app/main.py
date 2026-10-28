"""ROMKA application factory — one deployable modular monolith."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from app import __version__
from app.api import agents as agents_api
from app.api import (auth, channels, chat, data, fitness, memory, planner, profile,
                     providers, skills, system)
from app.api.deps import extract_session_token, rate_limiter
from app.config import Settings, get_settings
from app.core.errors import register_error_handlers
from app.core.security import constant_time_equal
from app.db.session import SessionLocal, create_all
from app.logging_conf import configure_logging
from app.web import routes

log = logging.getLogger("romka")

STATIC_DIR = Path(__file__).with_name("web") / "static"
API_PREFIX = "/api/v1"

CSRF_EXEMPT = {
    f"{API_PREFIX}/auth/register", f"{API_PREFIX}/auth/login", f"{API_PREFIX}/auth/guest",
    f"{API_PREFIX}/channels/telegram/webhook", f"{API_PREFIX}/channels/bale/webhook",
}


def create_app(settings_override: Settings | None = None) -> FastAPI:
    settings = settings_override or get_settings()
    configure_logging("INFO" if settings.is_production else "INFO")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if not settings.is_production:
            create_all()
        db = SessionLocal()
        try:
            from app.bootstrap import bootstrap, seed_demo_account
            info = bootstrap(db)
            demo = seed_demo_account(db, settings)
            db.commit()
            app.state.demo_login = demo
            log.info("bootstrap %s demo=%s", info, demo)
        except Exception:
            db.rollback()
            log.exception("bootstrap failed (app still starts; check DB migrations)")
        finally:
            db.close()
        yield

    app = FastAPI(
        title="ROMKA", version=__version__,
        description="Personal Intelligence. One Connected Life. — modular monolith",
        docs_url="/api/docs", redoc_url="/api/redoc", openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )
    app.state.settings = settings
    if settings_override is not None:
        app.dependency_overrides[get_settings] = lambda: settings_override

    register_error_handlers(app)
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.middleware("http")
    async def guards(request: Request, call_next):
        path = request.url.path
        # 1. Rate limiting (in-process; use Redis on multi-worker VPS).
        if not path.startswith("/static") and path != "/api/v1/health":
            client = request.client.host if request.client else "unknown"
            if not rate_limiter.allow(f"{client}:{path}", settings_override_limit(settings)):
                return JSONResponse(status_code=429, content={"ok": False, "error": {
                    "code": "rate_limited", "message": "تعداد درخواستها بیش از حد مجاز است."}})
        # 2. CSRF double-submit on state-changing API requests.
        if (request.method in ("POST", "PUT", "PATCH", "DELETE")
                and path.startswith(API_PREFIX) and path not in CSRF_EXEMPT):
            data = get_signer_for(settings).read(extract_session_token(request))
            token = request.headers.get("X-CSRF-Token", "")
            if data is None or not constant_time_equal(token, data.csrf):
                return JSONResponse(status_code=403, content={"ok": False, "error": {
                    "code": "csrf_failed", "message": "توکن امنیتی نامعتبر است."}})
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; connect-src 'self'; font-src 'self'; object-src 'none'")
        return response

    for module in (auth, system, profile, data, planner, chat, memory, agents_api,
                   skills, fitness, channels, providers):
        app.include_router(module.router, prefix=API_PREFIX)
    app.include_router(routes.router)

    return app


def settings_override_limit(settings: Settings) -> int:
    return max(10, settings.RATE_LIMIT_PER_MINUTE)


def get_signer_for(settings: Settings):
    from app.api.deps import _signer
    return _signer(settings.secret_key, settings.SESSION_MAX_AGE_SECONDS)


app = create_app()

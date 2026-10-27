from __future__ import annotations

import logging
from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings
from app.db.base import Base

log = logging.getLogger("romka.db")


def _make_engine(url: str):
    kwargs: dict = {"future": True, "pool_pre_ping": True}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    engine = create_engine(url, **kwargs)
    if url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(dbapi_conn, _record):
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.execute("PRAGMA journal_mode=WAL")
            cur.close()

    return engine


settings = get_settings()
engine = _make_engine(settings.DATABASE_URL)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, class_=Session)


def get_db() -> Generator[Session, None, None]:
    """Request-scoped unit of work.

    Endpoints call flush() to get IDs; the transaction is committed here only
    when the request completed without raising. Never commit a partial write.
    """
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    else:
        try:
            db.commit()
        except Exception as exc:
            db.rollback()
            log.error("commit failed: %s", type(exc).__name__)
            raise
    finally:
        db.close()


def create_all() -> None:
    """Dev/test bootstrap. Production uses Alembic migrations instead."""
    import app.db.models  # noqa: F401  (register all mappers)

    Base.metadata.create_all(bind=engine)

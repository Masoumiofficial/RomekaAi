"""Idempotent startup seed. Only reference data; never fake user progress.

The demo account is a deliberate exception: it is DEV-ONLY, disabled in
production, and every sample row is prefixed with «[نمونه]» so it can never be
mistaken for real measured progress. It is created once; an existing account is
never overwritten (including its password).
"""
from __future__ import annotations

import logging
from datetime import date

from sqlalchemy.orm import Session

from app.agents.registry import registry
from app.config import Settings
from app.core.security import hash_password, verify_password
from app.db.models import (FixedEvent, Goal, MemoryItem, Project, Task, User,
                           UserProfile)
from app.skills.registry import skill_registry

log = logging.getLogger("romka.bootstrap")

SAMPLE = "[نمونه] "


def bootstrap(db: Session) -> dict:
    added = skill_registry.seed(db)
    return {"skills_seeded": added, "skills_tracked": len(skill_registry.catalog["candidates"]),
            "agents_loaded": len(registry.agents), "registry_version": registry.version,
            "registry_warnings": registry.load_warnings}


def _has_no_sample_data(db: Session, user_id: int) -> bool:
    """Only seed an empty demo account; never mix samples into real progress."""
    return (db.query(Task).filter(Task.user_id == user_id).count() == 0
            and db.query(Project).filter(Project.user_id == user_id).count() == 0)


def _seed_sample_data(db: Session, user_id: int) -> int:
    """Small, clearly labelled dataset so the preview is actually explorable."""
    project = Project(user_id=user_id, name=SAMPLE + "انتشار گپینه",
                      description="صفحه فرود و مستندات شروع سریع",
                      goal_text="یک نسخه قابل تست منتشر شود",
                      success_metrics=["صفحه فرود بالا بیاید", "اولین بازخورد واقعی ثبت شود"],
                      priority=1)
    db.add(project)
    db.flush()
    db.add_all([
        Goal(user_id=user_id, project_id=project.id, title=SAMPLE + "تکمیل صفحه فرود",
             horizon="weekly", priority=1, success_metric="لینک قابل اشتراک"),
        Goal(user_id=user_id, title=SAMPLE + "سه جلسه تمرین بدون درد",
             horizon="weekly", priority=2, success_metric="۳ جلسه ثبتشده"),
        Task(user_id=user_id, project_id=project.id, title=SAMPLE + "نوشتن متن صفحه فرود",
             duration_min=90, priority=1, energy="high", kind="focus"),
        Task(user_id=user_id, project_id=project.id, title=SAMPLE + "بازبینی مستندات API",
             duration_min=45, priority=2, energy="medium", kind="focus"),
        Task(user_id=user_id, title=SAMPLE + "پیادهروی کوتاه عصر",
             duration_min=30, priority=3, energy="low", kind="personal"),
        FixedEvent(user_id=user_id, date=date.today(), title=SAMPLE + "جلسه هماهنگی",
                   start_min=600, end_min=660, category="meeting", source="user"),
        MemoryItem(user_id=user_id, layer="preference", key="ساعات تمرکز",
                   value={"text": "صبحها تمرکز بهتری دارم (نمونه)"}, source="user",
                   confidence="verified", sensitivity="public", tags=["نمونه"]),
        MemoryItem(user_id=user_id, layer="project", key="گپینه",
                   value={"text": "پروژه انتشار گپینه در مرحله صفحه فرود (نمونه)"},
                   source="user", confidence="verified", sensitivity="public", tags=["نمونه"]),
    ])
    db.flush()
    return 9


def seed_demo_account(db: Session, settings: Settings) -> dict:
    """Create the dev demo user once and report whether its login really works.

    An existing account is NEVER modified: if its password differs from the
    configured demo password, we report ``ready: False`` instead of claiming
    credentials that would fail. This is why the demo identity is a separate
    address (demo@…), never a user's own registration.
    """
    if settings.is_production or not settings.ROMKA_AUTO_DEMO:
        return {"demo_user": "disabled", "ready": False,
                "reason": "production or ROMKA_AUTO_DEMO=false"}
    email = (settings.ROMKA_DEMO_EMAIL or "").strip().lower()
    if not email or not settings.ROMKA_DEMO_PASSWORD:
        return {"demo_user": "disabled", "ready": False, "reason": "empty demo credentials"}
    existing = db.query(User).filter(User.email == email).first()
    if existing is not None:
        if not verify_password(settings.ROMKA_DEMO_PASSWORD, existing.password_hash):
            log.warning("demo account %s exists with a different password; "
                        "not overwriting it (demo login stays disabled)", email)
            return {"demo_user": "existing", "ready": False, "email": email, "sample_rows": 0,
                    "reason": "این ایمیل از قبل با رمز دیگری ثبت شده است؛ رمز بازنویسی نشد."}
        rows = 0
        if settings.ROMKA_DEMO_SEED_DATA and _has_no_sample_data(db, existing.id):
            rows = _seed_sample_data(db, existing.id)
        return {"demo_user": "existing", "ready": True, "email": email, "sample_rows": rows}
    user = User(email=email, display_name="مالک رومکا (نمونه)",
                password_hash=hash_password(settings.ROMKA_DEMO_PASSWORD),
                timezone="Asia/Tehran", locale="fa", role="owner")
    db.add(user)
    db.flush()
    db.add(UserProfile(user_id=user.id, onboarding_completed=True))
    db.flush()
    rows = _seed_sample_data(db, user.id) if settings.ROMKA_DEMO_SEED_DATA else 0
    log.warning("DEV demo account created: %s — never expose this instance publicly", email)
    return {"demo_user": "created", "ready": True, "email": email, "sample_rows": rows}

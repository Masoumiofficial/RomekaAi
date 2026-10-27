"""Idempotent startup seed. Only reference data; never fake user progress."""
from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.agents.registry import registry
from app.skills.registry import skill_registry

log = logging.getLogger("romka.bootstrap")


def bootstrap(db: Session) -> dict:
    added = skill_registry.seed(db)
    return {"skills_seeded": added, "skills_tracked": len(skill_registry.catalog["candidates"]),
            "agents_loaded": len(registry.agents), "registry_version": registry.version,
            "registry_warnings": registry.load_warnings}

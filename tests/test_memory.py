from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.core.errors import PermissionDenied, ValidationFailed
from app.memory.engine import memory_engine


def test_layered_store_and_supersede(db):
    old = memory_engine.store(db, user_id=1, layer="preference", key="ساعت تمرکز", value={"v": "صبح"})
    new = memory_engine.store(db, user_id=1, layer="preference", key="ساعت تمرکز", value={"v": "عصر"})
    assert new.id != old.id
    rows = memory_engine.retrieve(db, user_id=1, layers=["preference"])
    assert len(rows) == 1 and rows[0].value == {"v": "عصر"}
    assert old.is_deleted and old.confidence == "stale"


def test_agent_scope_and_sensitive_isolation(db):
    memory_engine.store(db, user_id=1, layer="agent", key="داده حساس", value={"v": "x"},
                        sensitivity="sensitive", agent_scope=["fitness-ali"])
    memory_engine.store(db, user_id=1, layer="preference", key="ترجیح عمومی", value={"v": "y"})
    # Gate 1: a specialist outside agent_scope never sees it.
    assert memory_engine.retrieve(db, user_id=1, agent_id="strategist",
                                  layers=["agent"], query="حساس",
                                  include_sensitive=True) == []
    # Gate 2: even the allowlisted specialist needs an explicit runtime grant.
    assert memory_engine.retrieve(db, user_id=1, agent_id="fitness-ali",
                                  layers=["agent"], query="حساس") == []
    assert len(memory_engine.retrieve(db, user_id=1, agent_id="fitness-ali",
                                      layers=["agent"], query="حساس",
                                      include_sensitive=True)) == 1
    # The user themselves sees everything, including sensitive items.
    assert len(memory_engine.retrieve(db, user_id=1)) == 2


def test_conflict_detection_and_ask_instead_of_invent(db):
    memory_engine.store(db, user_id=1, layer="project", key="وضعیت گپینه",
                        value={"stage": "بتا"}, confidence="inferred", source="inferred")
    conflicts = memory_engine.conflicts(db, user_id=1)
    assert conflicts and "تأییدنشده" in conflicts[0]["message"]


def test_expiry_and_user_control(db):
    past = datetime.now(timezone.utc) - timedelta(days=1)
    memory_engine.store(db, user_id=1, layer="event", key="قدیمی",
                               value={"v": 1}, expires_at=past)
    assert memory_engine.retrieve(db, user_id=1, query="قدیمی") == []
    item2 = memory_engine.store(db, user_id=1, layer="preference", key="قابل حذف", value={"v": 1})
    memory_engine.update(db, user_id=1, item_id=item2.id, value={"v": 2})
    assert memory_engine.get(db, user_id=1, item_id=item2.id).value == {"v": 2}
    memory_engine.forget(db, user_id=1, item_id=item2.id)
    with pytest.raises(Exception):
        memory_engine.get(db, user_id=1, item_id=item2.id)


def test_cross_user_permission_denied(db):
    i = memory_engine.store(db, user_id=1, layer="preference", key="خصوصی", value={"v": 1})
    with pytest.raises(PermissionDenied):
        memory_engine.get(db, user_id=2, item_id=i.id)


def test_invalid_layer_rejected(db):
    with pytest.raises(ValidationFailed):
        memory_engine.store(db, user_id=1, layer="evil", key="x", value={"v": 1})

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
    newer = memory_engine.store(db, user_id=1, layer="preference", key="ساعت تمرکز", value={"v": "شب"})
    assert old.superseded_by == new.id and new.superseded_by == newer.id


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
    updated = memory_engine.update(db, user_id=1, item_id=item2.id, value={"v": 2})
    assert updated.id != item2.id and updated.value == {"v": 2}
    assert item2.is_deleted and item2.value == {"v": 1} and item2.superseded_by == updated.id
    memory_engine.forget(db, user_id=1, item_id=updated.id)
    with pytest.raises(Exception):
        memory_engine.get(db, user_id=1, item_id=updated.id)


def test_cross_user_permission_denied(db):
    i = memory_engine.store(db, user_id=1, layer="preference", key="خصوصی", value={"v": 1})
    with pytest.raises(PermissionDenied):
        memory_engine.get(db, user_id=2, item_id=i.id)


def test_invalid_layer_rejected(db):
    with pytest.raises(ValidationFailed):
        memory_engine.store(db, user_id=1, layer="evil", key="x", value={"v": 1})


def test_edit_preserves_metadata_and_other_conflicting_versions(db):
    expiry = datetime.now(timezone.utc) + timedelta(days=2)
    first = memory_engine.store(db, user_id=1, layer="project", key="phase", value={"v": "a"},
                                source="import", confidence="inferred", sensitivity="sensitive",
                                agent_scope=["strategist"], tags=["private"], expires_at=expiry)
    other = memory_engine.store(db, user_id=1, layer="project", key="phase", value={"v": "b"}, supersede=False)
    edited = memory_engine.update(db, user_id=1, item_id=first.id, value={"v": "new"})
    assert (edited.sensitivity, edited.agent_scope, edited.tags, edited.expires_at) == (
        "sensitive", ["strategist"], ["private"], expiry)
    assert (edited.source, edited.confidence) == ("user", "verified")
    assert first.value == {"v": "a"} and first.is_deleted and first.superseded_by == edited.id
    assert not other.is_deleted and memory_engine.conflicts(db, user_id=1)
    exported = memory_engine.export_all(db, user_id=1)
    assert {x["id"] for x in exported} == {first.id, other.id, edited.id}


def test_context_only_uses_verified_unambiguous_unexpired_scoped_facts(db):
    def store(key, value, **kw):
        return memory_engine.store(db, user_id=1, layer="project", key=key, value={"v": value}, **kw)
    good = store("good", "GOOD")
    store("inferred", "INFERRED", confidence="inferred")
    store("stale", "STALE", confidence="stale")
    store("ambiguous", "FIRST")
    store("ambiguous", "SECOND", supersede=False)
    store("sensitive", "SECRET", sensitivity="sensitive")
    store("other scope", "OTHER_SCOPE", agent_scope=["other"])
    store("expired", "EXPIRED", expires_at=datetime.now(timezone.utc) - timedelta(days=1))
    # An expired contradictory record must not suppress a valid current fact.
    store("good", "OLD", supersede=False, expires_at=datetime.now(timezone.utc) - timedelta(days=1))
    memory_engine.store(db, user_id=2, layer="project", key="foreign", value={"v": "FOREIGN"})
    text, sources, sensitive = memory_engine.context_for_agent(
        db, user_id=1, agent_id="strategist", query=None, allowed_layers=["project"])
    assert "GOOD" in text and [x["id"] for x in sources] == [good.id]
    for token in ("INFERRED", "STALE", "FIRST", "SECOND", "SECRET", "OTHER_SCOPE", "EXPIRED", "OLD", "FOREIGN"):
        assert token not in text
    assert not sensitive
    assert {x["key"] for x in memory_engine.conflicts(db, user_id=1)} == {"inferred", "stale", "ambiguous"}


def test_memory_api_edit_csrf_export_and_owner_isolation(auth_client, db):
    from app.db.models import User
    from tests.conftest import H
    c, csrf, uid = auth_client
    item = c.post("/api/v1/memory", headers=H(csrf), json={
        "layer": "project", "key": "project", "value": {"v": "old"},
        "sensitivity": "sensitive", "tags": ["x"], "agent_scope": ["strategist"]}).json()["item"]
    path = f"/api/v1/memory/{item['id']}"
    assert c.put(path, json={"value": {"v": "new"}}).status_code == 403
    assert c.put(path, headers=H(csrf), json={"value": [1]}).status_code == 422
    response = c.put(path, headers=H(csrf), json={"value": {"v": "new"}})
    assert response.status_code == 200, response.text
    new = response.json()["item"]
    assert new["id"] != item["id"] and new["sensitivity"] == "sensitive"
    assert new["tags"] == ["x"] and new["agent_scope"] == ["strategist"]
    assert c.put(path, headers=H(csrf), json={"value": {}}).status_code == 404
    exported = c.get("/api/v1/memory/export").json()["items"]
    old = next(x for x in exported if x["id"] == item["id"])
    assert old["value"] == {"v": "old"} and old["is_deleted"] and old["superseded_by"] == new["id"]
    assert c.delete(f"/api/v1/memory/{new['id']}", headers=H(csrf)).status_code == 200
    assert any(x["id"] == new["id"] and x["is_deleted"] for x in c.get("/api/v1/memory/export").json()["items"])
    other = User(email="other-memory@example.com", password_hash="unused")
    db.add(other); db.flush()
    foreign = memory_engine.store(db, user_id=other.id, layer="project", key="foreign", value={"v": "secret"})
    db.flush()
    assert c.put(f"/api/v1/memory/{foreign.id}", headers=H(csrf), json={"value": {}}).status_code == 403
    assert c.delete(f"/api/v1/memory/{foreign.id}", headers=H(csrf)).status_code == 403
    assert not foreign.is_deleted and foreign.value == {"v": "secret"}
    assert all(x["id"] != foreign.id for x in c.get("/api/v1/memory/export").json()["items"])


def test_memory_page_has_edit_form(client):
    page = client.get("/memory").text
    for element in ("mem-edit-form", "mem-edit-value", "mem-edit-cancel"):
        assert element in page

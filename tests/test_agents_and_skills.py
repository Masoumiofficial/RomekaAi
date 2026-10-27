from __future__ import annotations

import json

import pytest

from app.agents.critic import evaluate as critic_evaluate
from app.agents.registry import AgentRegistry
from app.core.action_engine import ActionEngine, ToolSpec
from app.core.errors import PermissionDenied
from app.skills.registry import evaluate_candidate, sandbox_check, skill_registry


def test_registry_version_and_tool_narrowing(tmp_path):
    doc = json.loads((__import__("pathlib").Path("app/agents/definitions.json")).read_text(encoding="utf-8"))
    doc["agents"][0]["allowed_tools"].append("shell.exec")
    doc["agents"][0]["allowed_memory_layers"].append("evil_layer")
    p = tmp_path / "defs.json"
    p.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    reg = AgentRegistry(p)
    a = reg.get("romka-core")
    assert "shell.exec" not in a["allowed_tools"]
    assert "evil_layer" not in a["allowed_memory_layers"]
    assert reg.load_warnings


def test_selection_caps_at_two_specialists():
    from app.agents.registry import registry
    assert len(registry.active()) == 11
    assert registry.select("سلام") == [registry.get("romka-core")]
    chosen = registry.select("کمخوابی روی تمرین باشگاه و بهرهوری پروژه گپینه چه اثری دارد؟")
    assert 1 <= len(chosen) <= 2
    assert len({a["domain"] for a in chosen}) == len(chosen)


def test_critic_flags_false_certainty_and_missing_uncertainty():
    good = critic_evaluate("با توجه به دادهها ممکن است این برآورد تخمینی باشد.", facts_count=2)
    bad = critic_evaluate("قطعاً درمان میشوی، ۱۰۰٪ تضمین میکنم.", facts_count=0)
    assert good.score > bad.score
    assert bad.verdict in ("revised", "rejected")
    contradiction = critic_evaluate("افزایش وزنه بده و کاهش وزنه بده.", facts_count=1)
    assert contradiction.checks["no_contradiction"] is False


def test_action_engine_requires_approval_for_high_risk(db):
    eng = ActionEngine()
    eng.register(ToolSpec("test.danger", "high", lambda x: {"x": x}, {"x": "str"}))
    rec = eng.request(db, user_id=1, requester="test", goal="g", tool="test.danger",
                      inputs={"x": "1"}, allowlist=["test.danger"])
    assert rec.status == "pending_approval"
    with pytest.raises(PermissionDenied):
        eng.execute(db, rec)
    done = eng.execute(db, rec, approved=True)
    assert done.status == "executed" and done.result == {"x": "1"}
    # Config may not widen the code-defined tool set.
    assert eng.allowed_tools(["test.danger", "shell.exec"]) == ["test.danger"]


def test_skill_evaluation_license_veto_and_permissions():
    unclear = evaluate_candidate({"slug": "x", "license_spdx": "NOASSERTION", "stars": 100,
                                  "pushed_at": "2026-10-01T00:00:00Z", "fit": 20,
                                  "required_permissions": ["pure_python"], "dependency_count": 1})
    assert unclear["recommendation"] == "needs_review" and unclear["score"]["license"] == 0
    dangerous = evaluate_candidate({"slug": "y", "license_spdx": "MIT", "stars": 50000,
                                    "pushed_at": "2026-10-01T00:00:00Z", "fit": 20,
                                    "required_permissions": ["code_exec", "network"],
                                    "dependency_count": 1})
    assert dangerous["recommendation"] == "reject"
    assert sandbox_check({"required_permissions": ["code_exec"]})["passed"] is False
    assert sandbox_check({"required_permissions": ["pure_python"]})["passed"] is True


def test_skill_activation_gating_and_rollback(db):
    skill_registry.seed(db)
    active = skill_registry.activate(db, "python-dateutil-rrule")
    assert active.status == "active"
    with pytest.raises(PermissionDenied):
        skill_registry.activate(db, "mcp-servers")   # unclear license + broad permissions
    rolled = skill_registry.rollback(db, "python-dateutil-rrule")
    assert rolled.status == "rolled_back"
    sbom = skill_registry.sbom(db)
    assert sbom["schema"] == "romka-sbom/1.0"
    assert any(c["slug"] in ("fastapi", "sqlalchemy") for c in sbom["components"])

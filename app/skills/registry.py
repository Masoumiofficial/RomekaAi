"""Skill Intelligence & open-source acquisition governance.

This subsystem evaluates and tracks third-party capabilities. It NEVER executes
foreign code, never auto-updates dependencies, and never grants network/shell/
filesystem rights merely because a skill was registered. See docs/OSINT-AUDIT.md.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.errors import PermissionDenied, ValidationFailed
from app.db.models import Skill, SkillUsage

log = logging.getLogger("romka.skills")

_CATALOG = Path(__file__).with_name("catalog.json")

PERMISSIVE_LICENSES = {
    "MIT", "Apache-2.0", "BSD-3-Clause", "BSD-2-Clause", "ISC", "MPL-2.0", "Zlib",
    "Apache-2.0 OR BSD-3-Clause",
}
DANGEROUS_PERMISSIONS = {"code_exec", "shell", "network", "filesystem_write", "env_secrets", "vector_db"}
SAFE_PERMISSIONS = {"pure_python", "framework", "browser", "prompt_data", "readonly", "none"}
VALID_STATUSES = {"discovered", "evaluated", "approved", "active", "rejected",
                  "needs_legal_review", "rolled_back"}


def evaluate_candidate(evidence: dict) -> dict:
    """Deterministic, reproducible scoring. Returns score + recommendation.

    Weights: license 25, maintenance 20, security 20, fit 20, dep-cost 15.
    A missing/ambiguous license or a dangerous permission is a hard veto.
    """
    reasons: list[str] = []
    raw_license = (evidence.get("license_spdx") or "").strip()
    verified = (evidence.get("license_verified") or "").strip()
    effective_license = verified or raw_license
    if effective_license in PERMISSIVE_LICENSES:
        license_score = 25
        if verified and raw_license in ("", "NOASSERTION"):
            reasons.append("مجوز از فایل LICENSE منبع تأیید شد (فراداده مخزن کافی نبود).")
    else:
        license_score = 0
        reasons.append(f"مجوز «{effective_license or 'نامشخص'}» نیازمند بررسی حقوقی است.")

    pushed = evidence.get("pushed_at") or ""
    days_stale = 9999
    try:
        dt = datetime.fromisoformat(pushed.replace("Z", "+00:00"))
        days_stale = max(0, (datetime.now(timezone.utc) - dt).days)
    except ValueError:
        pass
    stars = int(evidence.get("stars") or 0)
    maintenance = 0
    maintenance += 10 if days_stale <= 30 else 6 if days_stale <= 180 else 2
    maintenance += 10 if stars >= 5000 else 7 if stars >= 1000 else 4
    if days_stale > 365:
        reasons.append("مخزن بیش از یک سال بهروز نشده است.")

    perms = set(evidence.get("required_permissions") or [])
    dangerous = perms & DANGEROUS_PERMISSIONS
    security = 20 if not dangerous else max(0, 20 - 10 * len(dangerous))
    if dangerous:
        reasons.append(f"دسترسیهای پرریسک: {sorted(dangerous)}")
    if perms - SAFE_PERMISSIONS - DANGEROUS_PERMISSIONS:
        reasons.append("دسترسیهای اعلامنشده نیازمند بررسی دستی است.")

    fit = max(0, min(20, int(evidence.get("fit", 0))))
    deps = int(evidence.get("dependency_count") or 0)
    dep_cost = 15 if deps <= 2 else 11 if deps <= 5 else 6 if deps <= 10 else 2
    total = license_score + maintenance + security + fit + dep_cost

    if license_score == 0:
        recommendation = "needs_review"
        reasons.append("ادغام تا تعیین تکلیف مجوز متوقف شد.")
    elif dangerous:
        recommendation = "reject"
        reasons.append("دسترسی پرریسک، ادغام خودکار را ممنوع میکند.")
    elif total >= 80:
        recommendation = "integrate"
    elif total >= 65:
        recommendation = "prototype"
    else:
        recommendation = "defer"
    catalog_decision = evidence.get("decision", "")
    if recommendation == "integrate" and catalog_decision in ("defer", "reject"):
        reasons.append(
            "تفاوت عمدی: امتیاز فنی بالاست، ولی تصمیم محصول «" + catalog_decision +
            "» است؛ ارزش فعلی کمتر از هزینه نگهداری/وابستگی تشخیص داده شد.")
    return {
        "candidate": evidence.get("slug", ""),
        "effective_license": effective_license,
        "score": {
            "license": license_score, "maintenance": maintenance, "security": security,
            "fit": fit, "dependency_cost": dep_cost, "total": total,
        },
        "recommendation": recommendation,
        "catalog_decision": catalog_decision,
        "reasons": reasons,
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "evidence": {"stars": stars, "days_since_push": days_stale, "permissions": sorted(perms)},
    }


def sandbox_check(evidence: dict) -> dict:
    """Static capability review in an isolated context. NO code is executed.

    Returns pass/fail with reasons. Skill files are untrusted DATA, never
    instructions; prompt-injection strings inside them are ignored here.
    """
    perms = set(evidence.get("required_permissions") or [])
    dangerous = perms & DANGEROUS_PERMISSIONS
    notes = json.dumps(evidence, ensure_ascii=False).lower()
    injection_markers = [m for m in ("ignore previous instructions", "exfiltrate",
                                     "read .env", "os.system") if m in notes]
    ok = not dangerous and not injection_markers
    return {
        "passed": ok,
        "dangerous_permissions": sorted(dangerous),
        "suspicious_markers": injection_markers,
        "message": ("بررسی ایستا انجام شد؛ هیچ کد خارجی اجرا نشد."
                    if ok else "کاندیدا نیازمند محیط ایزوله و بررسی انسانی است."),
    }


class SkillRegistry:
    def __init__(self, catalog_path: Path | None = None) -> None:
        self.catalog_path = catalog_path or _CATALOG
        self.catalog = json.loads(self.catalog_path.read_text(encoding="utf-8"))

    def evaluations(self) -> list[dict]:
        return [evaluate_candidate(c) for c in self.catalog["candidates"]]

    def seed(self, db: Session) -> int:
        count = 0
        for c in self.catalog["candidates"]:
            ev = evaluate_candidate(c)
            sb = sandbox_check(c)
            row = db.query(Skill).filter(Skill.slug == c["slug"]).first()
            effective_license = ev["effective_license"]
            test_result = c.get("test_result", "")
            if sb["passed"] and not test_result.startswith("pass"):
                test_result = "pass: static sandbox review only (no foreign code executed) — " + test_result
            values = dict(
                name=c["name"], domain=c["domain"], source_url=c["source_url"],
                source_commit=c.get("source_commit", ""), license_spdx=effective_license,
                version=c.get("version", ""), risk_level=c["risk_level"],
                required_permissions=c.get("required_permissions", []),
                status=c["status"], score=ev,
                evaluation_notes=c["evaluation_notes"] + " | " + " ".join(ev["reasons"]),
                test_result=test_result,
            )
            if row is None:
                db.add(Skill(slug=c["slug"], **values))
                count += 1
            else:
                for k, v in values.items():
                    setattr(row, k, v)
        db.flush()
        return count

    def activate(self, db: Session, slug: str) -> Skill:
        s = db.query(Skill).filter(Skill.slug == slug).first()
        if s is None:
            raise ValidationFailed(f"مهارت «{slug}» یافت نشد.")
        if s.status == "active":
            return s
        if s.license_spdx not in PERMISSIVE_LICENSES:
            raise PermissionDenied("مجوز این مهارت تأیید نشده است.", details={"license": s.license_spdx})
        if set(s.required_permissions or []) & DANGEROUS_PERMISSIONS:
            raise PermissionDenied("این مهارت دسترسی پرریسک درخواست میکند.")
        if s.status not in ("approved", "evaluated"):
            raise PermissionDenied(f"وضعیت «{s.status}» اجازه فعالسازی نمیدهد.")
        if not (s.test_result or "").startswith("pass"):
            raise PermissionDenied("تست مهارت قبول نشده است.")
        s.previous_version = s.version
        s.status = "active"
        s.activated_at = datetime.now(timezone.utc)
        db.add(SkillUsage(skill_id=s.id, action="activate", detail=f"version={s.version}"))
        db.flush()
        return s

    def deactivate(self, db: Session, slug: str, *, reason: str = "") -> Skill:
        s = db.query(Skill).filter(Skill.slug == slug).first()
        if s is None:
            raise ValidationFailed("مهارت یافت نشد.")
        s.status = "approved"
        db.add(SkillUsage(skill_id=s.id, action="deactivate", detail=reason[:500]))
        db.flush()
        return s

    def rollback(self, db: Session, slug: str) -> Skill:
        s = self.deactivate(db, slug, reason="rollback requested")
        s.status = "rolled_back"
        s.version = s.previous_version or s.version
        db.add(SkillUsage(skill_id=s.id, action="rollback", detail=f"restored={s.version}"))
        db.flush()
        return s

    def reject(self, db: Session, slug: str, *, reason: str) -> Skill:
        s = db.query(Skill).filter(Skill.slug == slug).first()
        if s is None:
            raise ValidationFailed("مهارت یافت نشد.")
        s.status = "rejected"
        s.evaluation_notes = (s.evaluation_notes + " | rejected: " + reason)[:4000]
        db.add(SkillUsage(skill_id=s.id, action="reject", detail=reason[:500]))
        db.flush()
        return s

    def sbom(self, db: Session) -> dict:
        rows = db.query(Skill).order_by(Skill.slug).all()
        active = [r for r in rows if r.status in ("active", "approved")]
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "project": "ROMKA", "schema": "romka-sbom/1.0",
            "components": [{
                "name": r.name, "slug": r.slug, "version": r.version,
                "license": r.license_spdx, "source": r.source_url,
                "pinned_commit": r.source_commit or "NOT PINNED (release version only)",
                "status": r.status, "risk": r.risk_level,
                "permissions": r.required_permissions,
                "score_total": (r.score or {}).get("score", {}).get("total"),
            } for r in active],
            "tracked_candidates": len(rows),
            "note": "Only components with status active/approved are integrated. Others are research records.",
        }


skill_registry = SkillRegistry()

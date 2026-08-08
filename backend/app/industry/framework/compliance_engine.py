"""Industry compliance engine (Phase 17.15).

Each pack ships compliance frameworks with rules that can be scoped to a
region or country (HIPAA for healthcare, banking standards for finance, ISO
for manufacturing, national regulations for government, accreditation for
education...). Rules are configurable — an organization can override severity
or disable a rule per country via its IndustryConfiguration settings.

The engine evaluates a rule set for an organization and records an
IndustryComplianceCheck per rule, so posture and history are queryable.
"""

import logging
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.events.publisher import publish_event
from app.industry.framework.registry import pack_compliance
from app.models.industry_configuration import IndustryConfiguration
from app.models.industry_policy import IndustryComplianceCheck, IndustryPolicy
from app.models.organization import gen_uuid

logger = logging.getLogger("vcos.industry.compliance")

_SEVERITY_WEIGHT = {"critical": 5, "high": 4, "medium": 3, "low": 2}


class IndustryComplianceEngine:
    async def sync_catalog(
        self,
        db: AsyncSession,
        *,
        industry_key: str,
    ) -> list[IndustryPolicy]:
        """Materialize the pack's compliance catalog as configurable rules."""
        definitions = pack_compliance(industry_key)
        rows = (
            (
                await db.execute(
                    select(IndustryPolicy).where(
                        IndustryPolicy.industry_key == industry_key
                    )
                )
            )
            .scalars()
            .all()
        )
        by_key = {(r.policy_key, r.region): r for r in rows}
        created: list[IndustryPolicy] = []
        for framework in definitions:
            for rule in framework.get("rules", []):
                key = (rule["key"], framework.get("region", "global"))
                row = by_key.get(key)
                if row is None:
                    row = IndustryPolicy(
                        id=gen_uuid(),
                        industry_key=industry_key,
                        policy_key=rule["key"],
                        name=rule["name"],
                        framework=framework["framework"],
                        region=framework.get("region", "global"),
                        control=rule.get("control"),
                        severity=rule.get("severity", "medium"),
                        evidence_requirements=rule.get("evidence") or [],
                        cadence_days=rule.get("cadence_days", 90),
                    )
                    db.add(row)
                    by_key[key] = row
                    created.append(row)
        if created:
            await db.flush()
        return sorted(by_key.values(), key=lambda r: r.framework)

    async def policies(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        industry_key: str,
    ) -> tuple[list[dict[str, Any]], IndustryConfiguration]:
        """Catalog + per-org effective rules (respecting country/overrides)."""
        policies = await self.sync_catalog(db, industry_key=industry_key)
        config = (
            await db.execute(
                select(IndustryConfiguration).where(
                    IndustryConfiguration.organization_id == organization_id,
                    IndustryConfiguration.industry_key == industry_key,
                )
            )
        ).scalars().first()
        settings = (config.settings or {}) if config else {}
        country = settings.get("country")
        overrides = (settings.get("compliance_overrides") or {}).get("rules", {})
        effective: list[dict[str, Any]] = []
        for policy in policies:
            if policy.region != "global" and country and policy.region != country:
                continue
            override = overrides.get(policy.policy_key, {})
            if override.get("enabled") is False:
                continue
            effective.append(
                {
                    "policy_id": policy.id,
                    "policy_key": policy.policy_key,
                    "name": policy.name,
                    "framework": policy.framework,
                    "region": policy.region,
                    "control": policy.control,
                    "severity": override.get("severity", policy.severity),
                    "evidence_requirements": policy.evidence_requirements or [],
                    "cadence_days": override.get("cadence_days", policy.cadence_days),
                    "enabled": policy.enabled,
                    "overridable": policy.overridable,
                }
            )
        return effective, config

    async def run(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        industry_key: str,
        actor_id: Optional[str] = None,
        evidence: Optional[dict[str, Any]] = None,
        auto_status: Optional[str] = None,
    ) -> dict[str, Any]:
        """Evaluate the effective rules and record a check per rule.

        `auto_status` lets a worker or evidence submitter stamp a result
        (pass/warn/fail); otherwise rules stay `pending` for human review.
        """
        effective, _config = await self.policies(
            db, organization_id=organization_id, industry_key=industry_key
        )
        evidence = evidence or {}
        checks: list[IndustryComplianceCheck] = []
        for rule in effective:
            rule_evidence = evidence.get(rule["policy_key"], {})
            if auto_status and not rule_evidence.get("status"):
                rule_evidence = {**rule_evidence, "status": auto_status}
            check = IndustryComplianceCheck(
                id=gen_uuid(),
                organization_id=organization_id,
                industry_key=industry_key,
                policy_id=rule["policy_id"],
                status=rule_evidence.get("status", "pending"),
                severity=rule["severity"],
                evidence=rule_evidence.get("details") or {
                    k: v for k, v in rule_evidence.items() if k != "status"
                },
                notes=rule_evidence.get("notes"),
                checked_by=actor_id,
                checked_at=utcnow() if auto_status else None,
            )
            db.add(check)
            checks.append(check)
        await db.flush()

        passed = sum(1 for c in checks if c.status == "pass")
        warned = sum(1 for c in checks if c.status == "warn")
        failed = sum(1 for c in checks if c.status == "fail")
        pending = len(checks) - passed - warned - failed
        score = self._score(checks) if checks else 100.0
        await publish_event(
            db,
            name="industry.compliance.checked",
            organization_id=organization_id,
            actor_id=actor_id,
            payload={
                "industry_key": industry_key,
                "rules": len(checks),
                "passed": passed,
                "warned": warned,
                "failed": failed,
                "pending": pending,
                "score": score,
            },
        )
        return {
            "industry_key": industry_key,
            "total": len(checks),
            "passed": passed,
            "warned": warned,
            "failed": failed,
            "pending": pending,
            "score": score,
            "check_ids": [c.id for c in checks],
        }

    def _score(self, checks: list[IndustryComplianceCheck]) -> float:
        passed = [c for c in checks if c.status == "pass"]
        total = sum(_SEVERITY_WEIGHT.get(c.severity, 3) for c in checks)
        if total == 0:
            return 100.0
        weighted = sum(_SEVERITY_WEIGHT.get(c.severity, 3) for c in passed)
        return round(100 * weighted / total, 1)

    async def checks(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        industry_key: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> list[IndustryComplianceCheck]:
        query = select(IndustryComplianceCheck).where(
            IndustryComplianceCheck.organization_id == organization_id
        )
        if industry_key:
            query = query.where(IndustryComplianceCheck.industry_key == industry_key)
        if status:
            query = query.where(IndustryComplianceCheck.status == status)
        query = query.order_by(IndustryComplianceCheck.created_at.desc()).limit(limit)
        result = await db.execute(query)
        return list(result.scalars().all())

    async def latest(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        industry_key: str,
    ) -> dict[str, Any]:
        """Latest posture summary for a pack (reuses the newest check ids)."""
        checks = await self.checks(
            db, organization_id=organization_id, industry_key=industry_key, limit=500
        )
        newest: dict[str, IndustryComplianceCheck] = {}
        for check in checks:
            if check.policy_id not in newest:
                newest[check.policy_id] = check
        latest_checks = list(newest.values())
        passed = sum(1 for c in latest_checks if c.status == "pass")
        warned = sum(1 for c in latest_checks if c.status == "warn")
        failed = sum(1 for c in latest_checks if c.status == "fail")
        pending = len(latest_checks) - passed - warned - failed
        return {
            "industry_key": industry_key,
            "total": len(latest_checks),
            "passed": passed,
            "warned": warned,
            "failed": failed,
            "pending": pending,
            "score": self._score(latest_checks) if latest_checks else None,
        }


industry_compliance_engine = IndustryComplianceEngine()

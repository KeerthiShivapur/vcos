"""Compliance service (Phase 15).

Framework control catalogs (ISO 27001, SOC 2, GDPR, HIPAA, PCI DSS,
FedRAMP), posture records per control, readiness reporting, overdue control
detection and the retention/legal-hold posture surface.
"""

from datetime import timedelta
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import ensure_aware, is_expired, utcnow
from app.events.publisher import publish_event
from app.models.enterprise import ComplianceControl

FRAMEWORKS: dict[str, list[dict[str, str]]] = {
    "iso27001": [
        {"control": "A.5.1", "title": "Information security policies"},
        {"control": "A.6.1", "title": "Internal organization"},
        {"control": "A.9.1", "title": "Access control policy"},
        {"control": "A.12.4", "title": "Logging and monitoring"},
        {"control": "A.18.1", "title": "Compliance with legal requirements"},
    ],
    "soc2": [
        {"control": "CC6.1", "title": "Logical and physical access"},
        {"control": "CC7.2", "title": "Monitor system components"},
        {"control": "CC8.1", "title": "Change management"},
        {"control": "A1.2", "title": "Availability capacity"},
        {"control": "CC4.1", "title": "Risk assessment"},
    ],
    "gdpr": [
        {"control": "ART.5", "title": "Lawfulness of processing"},
        {"control": "ART.15", "title": "Data access rights"},
        {"control": "ART.17", "title": "Right to erasure"},
        {"control": "ART.30", "title": "Records of processing"},
        {"control": "ART.32", "title": "Security of processing"},
    ],
    "hipaa": [
        {"control": "45.164.308", "title": "Administrative safeguards"},
        {"control": "45.164.312", "title": "Technical safeguards"},
        {"control": "45.164.316", "title": "Physical safeguards"},
    ],
    "pci": [
        {"control": "REQ.1", "title": "Firewall configuration"},
        {"control": "REQ.3", "title": "Protect stored cardholder data"},
        {"control": "REQ.8", "title": "Identify and authenticate access"},
        {"control": "REQ.10", "title": "Log and monitor access"},
    ],
    "fedramp": [
        {"control": "AC-2", "title": "Account management"},
        {"control": "AU-2", "title": "Audit events"},
        {"control": "SC-7", "title": "Boundary protection"},
        {"control": "SI-4", "title": "System monitoring"},
    ],
}


class ComplianceService:
    def frameworks(self) -> dict[str, Any]:
        return {
            framework: [control["control"] for control in controls]
            for framework, controls in FRAMEWORKS.items()
        }

    async def upsert_control(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        framework: str,
        control: str,
        status: str,
        title: Optional[str] = None,
        evidence: Optional[dict[str, Any]] = None,
        notes: Optional[str] = None,
        owner_id: Optional[str] = None,
        due_at: Optional[Any] = None,
        actor_id: Optional[str] = None,
    ) -> ComplianceControl:
        if framework not in FRAMEWORKS:
            raise ValueError(f"unknown framework: {framework}")
        if status not in ("pass", "warn", "fail", "pending"):
            raise ValueError("status must be pass|warn|fail|pending")
        record = (
            await db.execute(
                select(ComplianceControl).where(
                    ComplianceControl.organization_id == organization_id,
                    ComplianceControl.framework == framework,
                    ComplianceControl.control == control,
                )
            )
        ).scalars().first()
        if record is None:
            record = ComplianceControl(
                organization_id=organization_id,
                framework=framework,
                control=control,
                title=title or self._control_title(framework, control),
                status=status,
            )
            db.add(record)
        record.status = status
        if title:
            record.title = title
        if evidence is not None:
            record.evidence = evidence
        if notes is not None:
            record.notes = notes
        if owner_id is not None:
            record.owner_id = owner_id
        if due_at is not None:
            record.due_at = due_at
        record.checked_at = utcnow()
        await db.flush()
        await publish_event(
            db,
            name="compliance.updated",
            organization_id=organization_id,
            actor_id=actor_id,
            payload={
                "framework": framework,
                "control": control,
                "status": status,
            },
        )
        return record

    def _control_title(self, framework: str, control: str) -> str:
        for entry in FRAMEWORKS.get(framework, []):
            if entry["control"] == control:
                return entry["title"]
        return f"{framework} {control}"

    async def list_records(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        framework: Optional[str] = None,
        status: Optional[str] = None,
    ) -> list[ComplianceControl]:
        query = select(ComplianceControl).where(
            ComplianceControl.organization_id == organization_id
        )
        if framework:
            query = query.where(ComplianceControl.framework == framework)
        if status:
            query = query.where(ComplianceControl.status == status)
        result = await db.execute(query.order_by(ComplianceControl.framework, ComplianceControl.control))
        return list(result.scalars().all())

    async def posture(self, db: AsyncSession, organization_id: str) -> dict[str, Any]:
        records = await self.list_records(db, organization_id=organization_id)
        by_framework: dict[str, dict[str, Any]] = {}
        for record in records:
            bucket = by_framework.setdefault(
                record.framework, {"total": 0, "pass": 0, "warn": 0, "fail": 0, "pending": 0}
            )
            bucket["total"] += 1
            bucket[record.status] += 1
        readiness = 0.0
        if records:
            passed = sum(1 for record in records if record.status == "pass")
            readiness = round(passed / len(records) * 100, 1)
        return {
            "frameworks": by_framework,
            "readiness_percent": readiness,
            "checked_at": utcnow().isoformat(),
        }

    async def report(self, db: AsyncSession, organization_id: str) -> dict[str, Any]:
        posture = await self.posture(db, organization_id)
        records = await self.list_records(db, organization_id=organization_id)
        failures = [record for record in records if record.status == "fail"]
        overdue = [
            record for record in records
            if record.due_at and is_expired(record.due_at) and record.status != "pass"
        ]
        return {
            "readiness_percent": posture["readiness_percent"],
            "total_controls": len(records),
            "passed": sum(1 for record in records if record.status == "pass"),
            "failed": len(failures),
            "overdue": len(overdue),
            "frameworks": posture["frameworks"],
            "failed_controls": [
                {"framework": record.framework, "control": record.control, "title": record.title}
                for record in failures[:20]
            ],
        }

    async def flag_overdue(self, db: AsyncSession, *, limit: int = 100) -> int:
        """Worker hook — mark controls past due as warn."""
        records = (
            await db.execute(
                select(ComplianceControl).where(
                    ComplianceControl.due_at.is_not(None),
                    ComplianceControl.status.not_in(("pass", "fail")),
                ).limit(limit)
            )
        ).scalars().all()
        flagged = 0
        for record in records:
            if is_expired(record.due_at):
                record.status = "warn"
                flagged += 1
        return flagged


compliance_service = ComplianceService()

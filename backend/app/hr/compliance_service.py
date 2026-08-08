"""Compliance service (Phase 11.12 — Compliance & Legal).

Document expiry tracking (contracts, visas, identity, certifications,
policy acknowledgements), training requirements with completions and
renewal frequencies, and an overview that surfaces expired / expiring /
missing items so nothing lapses.
"""

import logging
from datetime import date, timedelta
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.hr.parse import to_date
from app.models.employee import Employee
from app.models.hr import ComplianceRecord, TrainingCompletion, TrainingRequirement

logger = logging.getLogger("vcos.hr.compliance")

DOCUMENT_TYPES = ["contract", "visa", "identity", "certification", "policy_acknowledgement"]
COMPLIANCE_STATUSES = ["valid", "expiring", "expired", "missing"]


class ComplianceService:
    # ------------------------------------------------------------------ documents

    async def record_document(
        self, db: AsyncSession, *, organization_id: str, data: dict[str, Any], reviewed_by: Optional[str] = None,
    ) -> ComplianceRecord:
        record = ComplianceRecord(
            organization_id=organization_id,
            employee_id=data.get("employee_id"),
            document_type=data["document_type"] if data.get("document_type") in DOCUMENT_TYPES else "contract",
            title=data["title"],
            status=data.get("status", "valid") if data.get("status") in COMPLIANCE_STATUSES else "valid",
            reference=data.get("reference"),
            issued_at=to_date(data.get("issued_at")),
            expires_at=to_date(data.get("expires_at")),
            last_reviewed_at=utcnow().date(),
            reviewed_by=reviewed_by,
            notes=data.get("notes"),
        )
        db.add(record)
        await db.flush()
        self._refresh_status(record)
        return record

    async def renew_document(
        self, db: AsyncSession, *, organization_id: str, record_id: str,
        expires_at: Optional[date] = None, reference: Optional[str] = None, reviewed_by: Optional[str] = None,
    ) -> Optional[ComplianceRecord]:
        record = (
            await db.execute(
                select(ComplianceRecord).where(ComplianceRecord.organization_id == organization_id, ComplianceRecord.id == record_id)
            )
        ).scalar_one_or_none()
        if record is None:
            return None
        if expires_at:
            record.expires_at = to_date(expires_at) or record.expires_at
        if reference:
            record.reference = reference
        record.last_reviewed_at = utcnow().date()
        record.reviewed_by = reviewed_by
        record.status = "valid"
        self._refresh_status(record)
        await db.flush()
        return record

    async def list_documents(
        self, db: AsyncSession, *, organization_id: str,
        employee_id: Optional[str] = None, document_type: Optional[str] = None, status: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        query = select(ComplianceRecord).where(ComplianceRecord.organization_id == organization_id)
        if employee_id:
            query = query.where(ComplianceRecord.employee_id == employee_id)
        if document_type:
            query = query.where(ComplianceRecord.document_type == document_type)
        if status:
            query = query.where(ComplianceRecord.status == status)
        rows = await db.execute(query.order_by(ComplianceRecord.expires_at))
        result = []
        for record in rows.scalars().all():
            self._refresh_status(record)
            employee = await db.get(Employee, record.employee_id) if record.employee_id else None
            result.append(
                {
                    "id": record.id,
                    "employee_id": record.employee_id,
                    "employee_name": employee.full_name if employee else None,
                    "document_type": record.document_type,
                    "title": record.title,
                    "status": record.status,
                    "reference": record.reference,
                    "issued_at": record.issued_at.isoformat() if record.issued_at else None,
                    "expires_at": record.expires_at.isoformat() if record.expires_at else None,
                    "last_reviewed_at": record.last_reviewed_at.isoformat() if record.last_reviewed_at else None,
                    "notes": record.notes,
                }
            )
        await db.flush()
        return result

    def _refresh_status(self, record: ComplianceRecord) -> None:
        if record.status == "missing" or record.expires_at is None:
            return
        today = utcnow().date()
        if record.expires_at < today:
            record.status = "expired"
        elif record.expires_at <= today + timedelta(days=30):
            record.status = "expiring"

    # ------------------------------------------------------------------ training

    async def create_requirement(self, db: AsyncSession, *, organization_id: str, data: dict[str, Any]) -> TrainingRequirement:
        requirement = TrainingRequirement(
            organization_id=organization_id,
            name=data["name"],
            category=data.get("category", "compliance"),
            required_for=data.get("required_for") or [],
            frequency_days=int(data.get("frequency_days", 365)),
            description=data.get("description"),
        )
        db.add(requirement)
        await db.flush()
        return requirement

    async def list_requirements(self, db: AsyncSession, *, organization_id: str) -> list[TrainingRequirement]:
        return (
            await db.execute(
                select(TrainingRequirement).where(TrainingRequirement.organization_id == organization_id).order_by(TrainingRequirement.name)
            )
        ).scalars().all()

    async def complete_training(
        self, db: AsyncSession, *, organization_id: str, data: dict[str, Any],
    ) -> TrainingCompletion:
        requirement = (
            await db.execute(
                select(TrainingRequirement).where(
                    TrainingRequirement.organization_id == organization_id, TrainingRequirement.id == data["requirement_id"]
                )
            )
        ).scalar_one_or_none()
        if requirement is None:
            raise ValueError("unknown training requirement")
        existing = (
            await db.execute(
                select(TrainingCompletion).where(
                    TrainingCompletion.organization_id == organization_id,
                    TrainingCompletion.employee_id == data["employee_id"],
                    TrainingCompletion.requirement_id == requirement.id,
                )
            )
        ).scalar_one_or_none()
        completed_at = to_date(data.get("completed_at")) or utcnow().date()
        expires_at = to_date(data.get("expires_at")) or (completed_at + timedelta(days=requirement.frequency_days))
        if existing is None:
            existing = TrainingCompletion(
                organization_id=organization_id,
                employee_id=data["employee_id"],
                requirement_id=requirement.id,
                completed_at=completed_at,
                expires_at=expires_at,
                provider=data.get("provider"),
                certificate_ref=data.get("certificate_ref"),
            )
            db.add(existing)
        else:
            existing.completed_at = completed_at
            existing.expires_at = expires_at
            existing.provider = data.get("provider")
            existing.certificate_ref = data.get("certificate_ref")
        await db.flush()
        return existing

    async def list_completions(
        self, db: AsyncSession, *, organization_id: str, employee_id: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        query = select(TrainingCompletion).where(TrainingCompletion.organization_id == organization_id)
        if employee_id:
            query = query.where(TrainingCompletion.employee_id == employee_id)
        rows = await db.execute(query.order_by(TrainingCompletion.completed_at.desc()))
        result = []
        for completion in rows.scalars().all():
            requirement = await db.get(TrainingRequirement, completion.requirement_id)
            employee = await db.get(Employee, completion.employee_id)
            result.append(
                {
                    "id": completion.id,
                    "employee_id": completion.employee_id,
                    "employee_name": employee.full_name if employee else None,
                    "requirement_id": completion.requirement_id,
                    "requirement": requirement.name if requirement else None,
                    "category": requirement.category if requirement else None,
                    "completed_at": completion.completed_at.isoformat() if completion.completed_at else None,
                    "expires_at": completion.expires_at.isoformat() if completion.expires_at else None,
                    "expired": completion.expires_at is not None and completion.expires_at < utcnow().date(),
                    "provider": completion.provider,
                    "certificate_ref": completion.certificate_ref,
                }
            )
        return result

    async def missing_trainings(self, db: AsyncSession, *, organization_id: str) -> list[dict[str, Any]]:
        """Active employees without a current completion for each requirement."""
        requirements = await self.list_requirements(db, organization_id=organization_id)
        employees = (
            await db.execute(
                select(Employee).where(
                    Employee.organization_id == organization_id, Employee.status == "active"
                )
            )
        ).scalars().all()
        missing: list[dict[str, Any]] = []
        today = utcnow().date()
        for requirement in requirements:
            for employee in employees:
                completion = (
                    await db.execute(
                        select(TrainingCompletion).where(
                            TrainingCompletion.organization_id == organization_id,
                            TrainingCompletion.employee_id == employee.id,
                            TrainingCompletion.requirement_id == requirement.id,
                        )
                    )
                ).scalar_one_or_none()
                ok = completion is not None and (completion.expires_at is None or completion.expires_at >= today)
                if not ok:
                    missing.append(
                        {
                            "employee_id": employee.id,
                            "employee_name": employee.full_name,
                            "requirement_id": requirement.id,
                            "requirement": requirement.name,
                            "category": requirement.category,
                            "last_completed": completion.completed_at.isoformat() if completion else None,
                        }
                    )
        return missing

    # ------------------------------------------------------------------ overview

    async def overview(self, db: AsyncSession, *, organization_id: str) -> dict[str, Any]:
        documents = await self.list_documents(db, organization_id=organization_id)
        today = utcnow().date()
        buckets: dict[str, int] = {"expired": 0, "expiring_30": 0, "expiring_60": 0, "expiring_90": 0, "valid": 0, "missing": 0}
        by_type: dict[str, int] = {}
        for document in documents:
            by_type[document["document_type"]] = by_type.get(document["document_type"], 0) + 1
            status = document["status"]
            if status == "expired":
                buckets["expired"] += 1
            elif status == "expiring":
                days = (date.fromisoformat(document["expires_at"]) - today).days if document["expires_at"] else 0
                if days <= 30:
                    buckets["expiring_30"] += 1
                elif days <= 60:
                    buckets["expiring_60"] += 1
                else:
                    buckets["expiring_90"] += 1
            elif status == "missing":
                buckets["missing"] += 1
            else:
                buckets["valid"] += 1
        completions = await self.list_completions(db, organization_id=organization_id)
        missing = await self.missing_trainings(db, organization_id=organization_id)
        return {
            "documents": {
                "total": len(documents),
                **buckets,
                "by_type": by_type,
            },
            "trainings": {
                "total_completions": len(completions),
                "expired_completions": sum(1 for item in completions if item["expired"]),
                "missing": len(missing),
            },
            "urgent": {
                "expired_documents": [d for d in documents if d["status"] == "expired"][:20],
                "expiring_30_days": [d for d in documents if d["status"] == "expiring"][:20],
                "missing_trainings": missing[:20],
            },
        }


compliance_service = ComplianceService()

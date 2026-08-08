"""Risk service â€” probability x impact scoring, mitigation, detection (Phase 3)."""

from typing import Any, Optional

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.models.approval import Risk
from app.models.employee import Employee


class RiskService:
    async def _validate_ref(self, db: AsyncSession, organization_id: str, key: str, value: str):
        from app.models.project import Project

        model = {"project_id": Project, "owner_id": Employee}.get(key)
        if model is None:
            return
        obj = await db.get(model, value)
        if obj is None or getattr(obj, "organization_id", None) != organization_id:
            raise ValueError(f"Invalid {key} reference")

    @staticmethod
    def compute_score(probability: int, impact: int) -> int:
        return max(1, min(25, (probability or 0) * (impact or 0)))

    @staticmethod
    def severity(score: int) -> str:
        if score >= 16:
            return "critical"
        if score >= 9:
            return "high"
        if score >= 4:
            return "medium"
        return "low"

    async def create(
        self, db: AsyncSession, *, organization_id: str, data: dict[str, Any],
        actor: Optional[Employee] = None, ip_address: Optional[str] = None,
    ) -> Risk:
        for key in ("project_id", "owner_id"):
            if data.get(key):
                await self._validate_ref(db, organization_id, key, data[key])
        probability = int(data.get("probability", 2))
        impact = int(data.get("impact", 2))
        risk = Risk(
            organization_id=organization_id,
            project_id=data.get("project_id"),
            title=data["title"],
            description=data.get("description"),
            status=data.get("status", "identified"),
            probability=probability,
            impact=impact,
            risk_score=self.compute_score(probability, impact),
            owner_id=data.get("owner_id"),
            mitigation=data.get("mitigation"),
            due_at=data.get("due_at"),
            detected_from=data.get("detected_from"),
        )
        db.add(risk)
        await db.flush()
        await self._emit(db, "risk.detected", organization_id, actor, ip_address, risk)
        if risk.owner_id:
            from app.services.work_alerts import notify_employee

            await notify_employee(
                db,
                organization_id=organization_id,
                employee_id=risk.owner_id,
                type="risk.detected",
                title=f"Risk assigned to you: {risk.title}",
                body=f"Score {risk.risk_score} · {self.severity(risk.risk_score)} severity",
                actor_id=actor.user_id if actor else None,
                priority="high" if risk.risk_score >= 9 else "normal",
                entity_type="risk",
                entity_id=risk.id,
                link="/analytics",
            )
        return risk

    async def _emit(self, db, name: str, organization_id: str, actor: Optional[Employee], ip: Optional[str], risk: Risk):
        from app.services.event_service import event_service

        await event_service.emit(
            db, name=name, actor_id=actor.user_id if actor else None,
            organization_id=organization_id,
            payload={"risk_id": risk.id, "title": risk.title, "project_id": risk.project_id, "risk_score": risk.risk_score},
        )

    async def get(self, db: AsyncSession, *, organization_id: str, risk_id: str) -> Optional[Risk]:
        row = await db.execute(
            select(Risk).where(Risk.organization_id == organization_id, Risk.id == risk_id)
        )
        risk = row.scalar_one_or_none()
        if risk:
            risk.owner_name = None
            risk.project_name = None
            if risk.owner_id:
                owner = await db.get(Employee, risk.owner_id)
                risk.owner_name = owner.full_name if owner else None
            if risk.project_id:
                from app.models.project import Project

                project = await db.get(Project, risk.project_id)
                risk.project_name = project.name if project else None
            risk.severity = self.severity(risk.risk_score)
        return risk

    async def list_all(
        self, db: AsyncSession, *, organization_id: str,
        project_id: Optional[str] = None, status: Optional[str] = None, severity: Optional[str] = None,
    ) -> list[Risk]:
        stmt = select(Risk).where(Risk.organization_id == organization_id)
        if project_id:
            stmt = stmt.where(Risk.project_id == project_id)
        if status:
            stmt = stmt.where(Risk.status == status)
        rows = await db.execute(stmt.order_by(desc(Risk.risk_score)))
        risks = list(rows.scalars().all())
        if severity:
            risks = [r for r in risks if self.severity(r.risk_score) == severity]
        owner_ids = {r.owner_id for r in risks if r.owner_id}
        project_ids = {r.project_id for r in risks if r.project_id}
        owners = {}
        if owner_ids:
            owners = {e.id: e for e in (await db.execute(select(Employee).where(Employee.id.in_(owner_ids)))).scalars().all()}
        from app.models.project import Project

        projects = {}
        if project_ids:
            projects = {p.id: p.name for p in (await db.execute(select(Project).where(Project.id.in_(project_ids)))).scalars().all()}
        for r in risks:
            r.owner_name = owners[r.owner_id].full_name if r.owner_id and owners.get(r.owner_id) else None
            r.project_name = projects.get(r.project_id)
            r.severity = self.severity(r.risk_score)
        return risks

    async def update(
        self, db: AsyncSession, *, organization_id: str, risk: Risk, data: dict[str, Any],
        actor: Optional[Employee] = None, ip_address: Optional[str] = None,
    ) -> Risk:
        for key, value in data.items():
            if hasattr(risk, key) and key not in ("id", "organization_id", "created_at"):
                setattr(risk, key, value)
        if "probability" in data or "impact" in data:
            risk.risk_score = self.compute_score(risk.probability, risk.impact)
        if risk.status == "closed":
            risk.status = "closed"
        risk.updated_at = utcnow()
        await db.flush()
        await self._emit(db, "risk.updated", organization_id, actor, ip_address, risk)
        return risk

    async def close(self, db: AsyncSession, *, organization_id: str, risk: Risk) -> Risk:
        risk.status = "closed"
        risk.updated_at = utcnow()
        await db.flush()
        return risk

    async def delete(self, db: AsyncSession, *, organization_id: str, risk: Risk):
        await db.delete(risk)


risk_service = RiskService()


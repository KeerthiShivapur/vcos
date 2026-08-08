"""Phase 20 — Enterprise resilience engine.

Continuously scans the organization for disruption signals — single-point-of-
failure roles, expiring vendor contracts, overdue invoices, a crowded sales
pipeline and failing projects — then maintains coordinated response plans so
the company can prepare for key employees leaving, vendor failures, demand
surges, incidents and financial stress.
"""

from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.events.publisher import publish_background_event
from app.models.department import Department
from app.models.employee import Employee
from app.models.finance import Invoice, VendorContract
from app.models.lead import Opportunity
from app.models.project import Project
from app.models.resilience_plan import ResiliencePlan, RESILIENCE_SCENARIOS

_PLAN_TEMPLATES: dict[str, dict[str, Any]] = {
    "key_employee": {
        "title": "Key employee dependency",
        "response": [
            {"step": "Identify backfill and knowledge transfer plan", "owner": "HR"},
            {"step": "Document critical processes owned by the role", "owner": "Engineering"},
            {"step": "Schedule cross-training within 30 days", "owner": "Managers"},
        ],
    },
    "vendor": {
        "title": "Critical vendor failure",
        "response": [
            {"step": "Contact vendor for renewal or exit terms", "owner": "Finance"},
            {"step": "Evaluate alternative vendors", "owner": "Procurement"},
            {"step": "Prepare fallback runbook", "owner": "Operations"},
        ],
    },
    "demand_surge": {
        "title": "Unexpected demand surge",
        "response": [
            {"step": "Prioritize the open pipeline", "owner": "Sales"},
            {"step": "Model capacity needs against delivery", "owner": "Operations"},
            {"step": "Review hiring triggers", "owner": "Leadership"},
        ],
    },
    "incident": {
        "title": "Delivery disruption",
        "response": [
            {"step": "Stabilize at-risk projects", "owner": "Engineering"},
            {"step": "Reallocate resources to blocked work", "owner": "Managers"},
            {"step": "Communicate revised timelines", "owner": "Leadership"},
        ],
    },
    "financial": {
        "title": "Financial stress",
        "response": [
            {"step": "Chase overdue receivables", "owner": "Finance"},
            {"step": "Review discretionary spend", "owner": "Finance"},
            {"step": "Re-forecast cash position", "owner": "CFO"},
        ],
    },
}


class ResilienceEngine:
    """Maintains living disruption scenarios and response plans."""

    async def assess(
        self, db: AsyncSession, organization_id: str, *, commit: bool = False
    ) -> dict[str, Any]:
        """Scan the organization and refresh its resilience plans."""
        now = utcnow()
        signals: list[dict[str, Any]] = []

        single_roles = (
            await db.execute(
                select(Department.name, func.count(Employee.id))
                .join(Employee, Employee.department_id == Department.id)
                .where(Employee.organization_id == organization_id)
                .group_by(Department.id, Department.name)
                .having(func.count(Employee.id) == 1)
                .limit(20)
            )
        ).all()
        if single_roles:
            signals.append({
                "type": "single_point_of_failure",
                "domains": ["people"],
                "detail": ", ".join(name for name, _ in single_roles),
                "count": len(single_roles),
            })

        vendor_risks = (
            await db.execute(
                select(func.count(VendorContract.id)).where(
                    VendorContract.organization_id == organization_id,
                    VendorContract.renewal_status == "overdue",
                )
            )
        ).scalar() or 0
        expiring = (
            await db.execute(
                select(func.count(VendorContract.id)).where(
                    VendorContract.organization_id == organization_id,
                    VendorContract.status.in_(["expiring", "expired"]),
                )
            )
        ).scalar() or 0
        if vendor_risks or expiring:
            signals.append({
                "type": "vendor_dependence",
                "domains": ["finance", "operations"],
                "detail": f"{vendor_risks} overdue renewal(s), {expiring} expiring contract(s)",
                "count": vendor_risks + expiring,
            })

        overdue_invoices = (
            await db.execute(
                select(func.count(Invoice.id)).where(
                    Invoice.organization_id == organization_id,
                    Invoice.status == "overdue",
                )
            )
        ).scalar() or 0
        if overdue_invoices:
            signals.append({
                "type": "financial_stress",
                "domains": ["finance"],
                "detail": f"{overdue_invoices} overdue invoice(s)",
                "count": overdue_invoices,
            })

        open_pipeline = (
            await db.execute(
                select(func.count(Opportunity.id)).where(
                    Opportunity.organization_id == organization_id,
                    Opportunity.stage.in_(["qualified", "proposal", "negotiation"]),
                )
            )
        ).scalar() or 0
        if open_pipeline >= 3:
            signals.append({
                "type": "demand_surge",
                "domains": ["customers", "delivery"],
                "detail": f"{open_pipeline} open opportunity(ies) in the pipeline",
                "count": open_pipeline,
            })

        failing_projects = (
            await db.execute(
                select(func.count(Project.id)).where(
                    Project.organization_id == organization_id,
                    Project.health.in_(["at_risk", "critical"]),
                )
            )
        ).scalar() or 0
        if failing_projects:
            signals.append({
                "type": "delivery_disruption",
                "domains": ["projects"],
                "detail": f"{failing_projects} at-risk or blocked project(s)",
                "count": failing_projects,
            })

        created: list[dict[str, Any]] = []
        updated: list[dict[str, Any]] = []
        scenario_map = {
            "single_point_of_failure": "key_employee",
            "vendor_dependence": "vendor",
            "demand_surge": "demand_surge",
            "delivery_disruption": "incident",
            "financial_stress": "financial",
        }
        for signal in signals:
            scenario = scenario_map[signal["type"]]
            template = _PLAN_TEMPLATES[scenario]
            existing = (
                await db.execute(
                    select(ResiliencePlan).where(
                        ResiliencePlan.organization_id == organization_id,
                        ResiliencePlan.scenario == scenario,
                        ResiliencePlan.status.in_(["draft", "active"]),
                    ).limit(1)
                )
            ).scalars().first()
            impact = {
                "domains": signal["domains"],
                "risk_level": "high" if signal["count"] >= 3 else "medium",
                "signals": [signal],
            }
            if existing:
                existing.impact = impact
                existing.assessed_at = now
                existing.description = f"Detected on {now.strftime('%Y-%m-%d')}: {signal['detail']}"
                await db.flush()
                updated.append(self.serialize(existing))
            else:
                row = ResiliencePlan(
                    organization_id=organization_id,
                    scenario=scenario,
                    title=template["title"],
                    description=f"Detected on {now.strftime('%Y-%m-%d')}: {signal['detail']}",
                    impact=impact,
                    response_plan=template["response"],
                    status="active",
                    source="kernel.resilience",
                    assessed_at=now,
                )
                db.add(row)
                await db.flush()
                created.append(self.serialize(row))

        await publish_background_event(
            db, name="company.health.updated", organization_id=organization_id,
            payload={"source": "kernel.resilience", "scenarios": len(signals),
                     "created": len(created), "updated": len(updated)},
        )
        if commit:
            await db.commit()
        return {"organization_id": organization_id, "assessed_at": now.isoformat(),
                "signals": signals, "created": created, "updated": updated,
                "total": len(created) + len(updated)}

    async def list(
        self,
        db: AsyncSession,
        organization_id: str,
        *,
        scenario: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        stmt = select(ResiliencePlan).where(
            ResiliencePlan.organization_id == organization_id
        )
        if scenario:
            stmt = stmt.where(ResiliencePlan.scenario == scenario)
        if status:
            stmt = stmt.where(ResiliencePlan.status == status)
        rows = (
            await db.execute(stmt.order_by(ResiliencePlan.created_at.desc()).limit(limit))
        ).scalars().all()
        return {"total": len(rows), "plans": [self.serialize(r) for r in rows],
                "scenarios": list(RESILIENCE_SCENARIOS)}

    def serialize(self, row: ResiliencePlan) -> dict[str, Any]:
        return {
            "id": row.id,
            "scenario": row.scenario,
            "title": row.title,
            "description": row.description,
            "impact": row.impact or {},
            "response_plan": row.response_plan or [],
            "status": row.status,
            "assessed_at": row.assessed_at.isoformat() if row.assessed_at else None,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }


resilience_engine = ResilienceEngine()

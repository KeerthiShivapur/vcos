"""Enterprise simulation engine — what-if analysis across all domains.

Executives ask "what if we hire 200 engineers?" and the engine simulates the
impact across budget, infrastructure, knowledge, hiring, projects, training,
customers and growth, producing an evidence-based forecast plus risk summary.
"""

from __future__ import annotations

import time
from datetime import timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.events.publisher import publish_background_event
from app.models.customer import Customer
from app.models.employee import Employee
from app.models.finance import Budget
from app.models.project import Project
from app.models.simulation import SimulationRun, SimulationRunStatus as SIMULATION_STATUSES

SIMULATION_DOMAINS = (
    "budget", "infrastructure", "knowledge", "hiring", "projects",
    "training", "customers", "growth", "legal", "support",
)

SCENARIO_TYPES = ("hiring", "expansion", "reduction", "acquisition", "investment", "other")


class SimulationEngine:
    async def run(
        self,
        db: AsyncSession,
        organization_id: str,
        *,
        title: str,
        question: str | None = None,
        assumptions: list[dict[str, Any]] | None = None,
        domains: list[str] | None = None,
        created_by: str | None = None,
        commit: bool = False,
    ) -> dict[str, Any]:
        started = time.perf_counter()
        run = SimulationRun(
            organization_id=organization_id,
            title=title,
            question=question,
            assumptions=assumptions or [],
            domains=[d for d in (domains or SIMULATION_DOMAINS) if d in SIMULATION_DOMAINS]
            or list(SIMULATION_DOMAINS),
            status="running",
            created_by=created_by,
            source_event="simulation.finished",
        )
        db.add(run)
        await db.flush()

        scenario: dict[str, Any] = {}
        for assumption in run.assumptions or []:
            if isinstance(assumption, dict):
                scenario[assumption.get("name", "parameter")] = assumption.get("value")

        results = await self._simulate(db, organization_id, scenario, run.domains)
        run.results = results["forecast"]
        run.risk = results["risk"]
        run.status = "finished"
        run.completed_at = utcnow()
        run.duration_ms = int((time.perf_counter() - started) * 1000)
        await db.flush()
        await publish_background_event(
            db, name="simulation.finished", organization_id=organization_id,
            payload={"simulation_id": run.id, "title": title,
                     "domains": run.domains, "duration_ms": run.duration_ms},
        )
        if commit:
            await db.commit()
        return self._serialize(run)

    async def _simulate(
        self, db: AsyncSession, organization_id: str, scenario: dict[str, Any], domains: list[str]
    ) -> dict[str, Any]:
        employees = (
            await db.execute(
                select(func.count(Employee.id)).where(Employee.organization_id == organization_id)
            )
        ).scalar() or 0
        projects = (
            await db.execute(
                select(func.count(Project.id)).where(Project.organization_id == organization_id)
            )
        ).scalar() or 0
        customers = (
            await db.execute(
                select(func.count(Customer.id)).where(Customer.organization_id == organization_id)
            )
        ).scalar() or 0
        budgets = (
            await db.execute(
                select(Budget).where(Budget.organization_id == organization_id, Budget.status == "active")
            )
        ).scalars().all()
        allocated = sum(b.allocated_amount or 0 for b in budgets)
        used = sum(b.used_amount or 0 for b in budgets)

        hires = abs(int(scenario.get("hires", scenario.get("headcount", 0)) or 0))
        growth_pct = float(scenario.get("growth_pct", 0) or 0)
        budget_change = float(scenario.get("budget_change_pct", 0) or 0)
        region = str(scenario.get("region", ""))

        per_employee_cost = (used / employees) if employees else 50000.0
        new_cost = round(hires * per_employee_cost, 0)
        forecast: dict[str, Any] = {
            "hiring": {
                "headcount_now": employees,
                "headcount_after": employees + hires,
                "cost_impact": {"annual_usd": new_cost},
                "ramp_time_weeks": 8,
            },
            "projects": {
                "capacity_gain_pct": round(min(90.0, hires / max(employees, 1) * 40), 1),
                "project_slots": projects + max(0, hires // 4),
            },
            "budget": {
                "allocated": allocated,
                "used": used,
                "new_burden_pct": round(new_cost / max(allocated, 1) * 100, 1),
                "needs_budget_increase_pct": budget_change,
            },
            "infrastructure": {
                "cloud_growth_pct": round(min(200.0, hires / max(employees, 1) * 15), 1),
                "regions": 1 if region else 0,
            },
            "training": {
                "onboarding_cost_usd": round(hires * 3000, 0),
                "courses_needed": max(1, hires // 5),
            },
            "knowledge": {
                "documents_to_create": max(1, hires // 3),
                "risk": "Knowledge dilution during rapid hiring" if hires >= employees * 0.3 else "Manageable",
            },
            "customers": {
                "current": customers,
                "served_after": customers + int(customers * (growth_pct or 0.1) * (1 + hires / max(employees, 1))),
            },
            "growth": {
                "projected_revenue_growth_pct": round((growth_pct or 5.0) + min(20.0, hires * 2), 1),
                "break_even_months": 12 if new_cost > 0 else 0,
            },
        }
        risk = {
            "level": "high" if hires >= employees * 0.5 else "medium" if hires >= employees * 0.2 else "low",
            "items": [],
        }
        if hires >= employees * 0.5:
            risk["items"].append("Headcount shock may strain management capacity")
        if region:
            risk["items"].append(f"Expansion into {region} adds legal, tax and compliance complexity")
        if budget_change == 0 and new_cost > 0:
            risk["items"].append("No budget increase modeled for the added headcount")
        if not risk["items"]:
            risk["items"].append("No material risks detected in the modeled scenario")
        return {"forecast": forecast, "risk": risk}

    async def list(
        self, db: AsyncSession, organization_id: str, *, limit: int = 100
    ) -> dict[str, Any]:
        rows = (
            await db.execute(
                select(SimulationRun)
                .where(SimulationRun.organization_id == organization_id)
                .order_by(SimulationRun.created_at.desc())
                .limit(limit)
            )
        ).scalars().all()
        return {"total": len(rows), "simulations": [self._serialize(r) for r in rows]}

    async def get(self, db: AsyncSession, organization_id: str, simulation_id: str) -> dict[str, Any] | None:
        row = (
            await db.execute(
                select(SimulationRun).where(
                    SimulationRun.organization_id == organization_id,
                    SimulationRun.id == simulation_id,
                )
            )
        ).scalars().first()
        return self._serialize(row) if row else None

    def _serialize(self, row: SimulationRun) -> dict[str, Any]:
        return {
            "id": row.id, "title": row.title, "question": row.question,
            "assumptions": row.assumptions or [], "domains": row.domains or [],
            "results": row.results or {}, "risk": row.risk or {}, "status": row.status,
            "created_by": row.created_by,
            "completed_at": row.completed_at.isoformat() if row.completed_at else None,
            "duration_ms": row.duration_ms,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }


simulation_engine = SimulationEngine()

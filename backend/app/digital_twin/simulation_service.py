"""Scenario Simulation Engine (Phase 18.3) — "what happens if…".

Executives describe a change and the engine simulates timeline, cost, risk,
knowledge, collaboration, productivity and revenue impact against the
digital twin's current state. Simulations are persisted through the Phase 8
`Simulation` table (scenario, assumptions, results) so every run is auditable.

Scenarios: hire_engineers | expand_region | delay_project | training_budget |
merge_departments | close_office
"""

import json
import logging
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.digital_twin.twin_service import digital_twin_service
from app.events.publisher import publish_background_event
from app.models.executive import Simulation

logger = logging.getLogger("vcos.digital_twin.simulation")

SCENARIOS = [
    "hire_engineers",
    "expand_region",
    "delay_project",
    "training_budget",
    "merge_departments",
    "close_office",
]

SCENARIO_TITLES = {
    "hire_engineers": "Hire engineers",
    "expand_region": "Expand to a new region",
    "delay_project": "Delay a project",
    "training_budget": "Increase training budget",
    "merge_departments": "Merge two departments",
    "close_office": "Close an office",
}


class SimulationService:
    """Runs scenario simulations against the digital twin."""

    async def _base_state(self, db: AsyncSession, organization_id: str) -> dict[str, Any]:
        twin = await digital_twin_service.get_twin(db, organization_id)
        if twin is None:
            payload = await digital_twin_service.build_twin(db, organization_id)
            return payload
        import json as _json

        return {
            "entity_counts": _json.loads(twin.entity_counts_json or "{}"),
            "dimensions": _json.loads(twin.dimensions_json or "{}"),
            "state": _json.loads(twin.state_json or "{}"),
        }

    async def run(
        self,
        db: AsyncSession,
        organization_id: str,
        user_id: Optional[str],
        *,
        scenario: str,
        parameters: Optional[dict[str, Any]] = None,
        commit: bool = False,
    ) -> dict[str, Any]:
        if scenario not in SCENARIOS:
            raise ValueError(f"Unknown scenario '{scenario}' — choose from {SCENARIOS}")
        parameters = parameters or {}
        base = await self._base_state(db, organization_id)
        counts = base["entity_counts"]
        dims = base["dimensions"]
        state = base["state"]

        employees = counts.get("active_employees", counts.get("employees", 0)) or 0
        open_tasks = counts.get("open_tasks", 0) or 0
        projects = counts.get("projects", 0) or 0
        customers = counts.get("customers", 0) or 0

        results = self._simulate(scenario, parameters, {"counts": counts, "dims": dims, "state": state})

        # cross-cut scores
        risk_score = results["risk"]
        timeline = results["timeline"]
        cost = results["cost"]
        productivity = results["productivity"]
        summary = (
            f"{SCENARIO_TITLES[scenario]}: {results.get('summary', '')} "
            f"Risk {risk_score}/100, timeline {timeline}, cost {cost}."
        )

        row = Simulation(
            organization_id=organization_id,
            user_id=user_id,
            scenario=scenario,
            title=parameters.get("title", SCENARIO_TITLES[scenario]),
            assumptions_json=json.dumps({"parameters": parameters, "base_state": state}),
            results_json=json.dumps(results),
            status="completed",
        )
        db.add(row)
        await db.flush()
        await publish_background_event(
            db,
            name="simulation.completed",
            organization_id=organization_id,
            payload={"simulation_id": row.id, "scenario": scenario, "risk": risk_score},
        )
        if commit:
            await db.commit()
        return {"id": row.id, "scenario": scenario, "title": row.title, "results": results}

    def _simulate(self, scenario: str, params: dict, base: dict) -> dict[str, Any]:
        counts = base["counts"]
        employees = counts.get("active_employees", counts.get("employees", 0)) or 0
        open_tasks = counts.get("open_tasks", 0) or 0

        if scenario == "hire_engineers":
            hires = int(params.get("count", 10))
            ramp_weeks = int(params.get("ramp_weeks", 12))
            cost_per = float(params.get("cost_per_hire", 50000))
            cost = hires * cost_per
            risk = 15 + min(40, hires)
            timeline = f"{ramp_weeks} weeks to full productivity"
            productivity = f"+{min(40, round(hires / max(1, employees) * 100))}% capacity within {ramp_weeks} weeks"
            summary = f"Hiring {hires} engineers adds capacity and lowers workload from {open_tasks} open tasks."
            outcomes = {
                "workload_after": max(0, round(open_tasks / max(1, employees + hires), 2)),
                "headcount_after": employees + hires,
            }
            return {
                "risk": risk, "cost": f"${cost:,.0f}", "timeline": timeline,
                "productivity": productivity, "summary": summary, "outcomes": outcomes,
                "revenue_impact": f"+{min(25, round(hires * 1.5))}% projected capacity-driven revenue",
            }

        if scenario == "expand_region":
            market = params.get("market", "Europe")
            cost = f"${float(params.get('budget', 250000)):,.0f}"
            risk = 45 + min(30, int(params.get("complexity", 5)) * 5)
            timeline = params.get("timeline", "9 months to operational")
            summary = f"Expanding to {market} requires staffing, infrastructure and compliance preparation."
            return {
                "risk": risk, "cost": cost, "timeline": timeline,
                "productivity": "-12% initial productivity during setup",
                "summary": summary,
                "outcomes": {"market": market, "customers_addressable": customers + int(params.get("expected_customers", 25))},
                "revenue_impact": f"+{min(40, int(params.get('expected_growth', 15)))}% long-term market revenue",
            }

        if scenario == "delay_project":
            weeks = int(params.get("weeks", 4))
            risk = 40 + weeks * 5
            cost = f"${weeks * 25000:,.0f} opportunity cost"
            summary = f"Delaying the project by {weeks} weeks frees capacity but raises delivery risk."
            return {
                "risk": min(90, risk), "cost": cost, "timeline": f"+{weeks} weeks to completion",
                "productivity": f"+{min(20, weeks * 3)}% short-term team availability",
                "summary": summary,
                "outcomes": {"weeks_delayed": weeks, "open_tasks_relief": min(open_tasks, weeks * 8)},
                "revenue_impact": f"-{weeks * 2}% projected quarterly revenue",
            }

        if scenario == "training_budget":
            budget = float(params.get("budget", 20000))
            risk = 5
            cost = f"${budget:,.0f}"
            timeline = "Quarter-over-quarter learning adoption"
            summary = f"Investing ${budget:,.0f} in training strengthens knowledge health and retention."
            return {
                "risk": risk, "cost": cost, "timeline": timeline,
                "productivity": "+5% expected productivity from skill growth",
                "summary": summary,
                "outcomes": {"learning_enrollments_lift": int(budget / 500), "attrition_reduction": "~2%"},
                "revenue_impact": "+2% retention-driven revenue",
            }

        if scenario == "merge_departments":
            risk = 35 + int(params.get("complexity", 4)) * 6
            cost = "$15,000 transition cost"
            timeline = "8 weeks to stabilization"
            summary = "Merging departments reduces overhead but requires careful people mapping."
            return {
                "risk": risk, "cost": cost, "timeline": timeline,
                "productivity": "+8% coordination efficiency after stabilization",
                "summary": summary,
                "outcomes": {"departments_after": max(1, int(params.get("departments_after", 1)))},
                "revenue_impact": "neutral to +3%",
            }

        if scenario == "close_office":
            cost = f"-${float(params.get('savings', 120000)):,.0f} annual savings"
            risk = 30 + int(params.get("remote_friction", 3)) * 8
            timeline = "16 weeks to close"
            summary = "Closing an office cuts costs but may reduce collaboration density."
            return {
                "risk": risk, "cost": cost, "timeline": timeline,
                "productivity": "-4% collaboration friction initially",
                "summary": summary,
                "outcomes": {"savings_annual": float(params.get("savings", 120000))},
                "revenue_impact": "-1% collaboration-driven revenue",
            }

        return {"risk": 0, "cost": "$0", "timeline": "—", "productivity": "—", "summary": "Unknown scenario.", "outcomes": {}}

    async def list(self, db: AsyncSession, organization_id: str, limit: int = 50) -> list[dict[str, Any]]:
        rows = (
            await db.execute(
                select(Simulation)
                .where(Simulation.organization_id == organization_id)
                .order_by(Simulation.created_at.desc())
                .limit(limit)
            )
        ).scalars().all()
        return [self.serialize(r) for r in rows]

    async def get(self, db: AsyncSession, organization_id: str, simulation_id: str) -> Optional[dict[str, Any]]:
        row = (
            await db.execute(
                select(Simulation).where(
                    Simulation.organization_id == organization_id, Simulation.id == simulation_id
                )
            )
        ).scalars().first()
        return self.serialize(row) if row else None

    def serialize(self, row: Simulation) -> dict[str, Any]:
        def _loads(value: Optional[str], fallback: Any):
            if not value:
                return fallback
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                return fallback

        return {
            "id": row.id,
            "scenario": row.scenario,
            "title": row.title,
            "assumptions": _loads(row.assumptions_json, {}),
            "results": _loads(row.results_json, {}),
            "status": row.status,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }


simulation_service = SimulationService()

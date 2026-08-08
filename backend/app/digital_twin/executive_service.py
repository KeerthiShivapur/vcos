"""Executive Service & Autonomous Executive Assistant (Phase 18.14/18.15).

Assembles the Enterprise Intelligence Center dashboard (twin, health,
predictions, recommendations, simulations, forecasts, decisions, brief) and
generates the CEO's morning brief automatically from live organizational
evidence.
"""

import logging
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.digital_twin.decision_service import decision_service
from app.digital_twin.forecasting_service import forecasting_service
from app.digital_twin.health_service import health_service
from app.digital_twin.optimization_service import optimization_service
from app.digital_twin.prediction_service import prediction_service
from app.digital_twin.recommendation_service import recommendation_service
from app.digital_twin.simulation_service import simulation_service
from app.digital_twin.twin_service import digital_twin_service
from app.models.organization import Organization

logger = logging.getLogger("vcos.digital_twin.executive")


class ExecutiveService:
    """Builds the executive intelligence center and morning brief."""

    async def dashboard(self, db: AsyncSession, organization_id: str) -> dict[str, Any]:
        """One payload for the Enterprise Intelligence Center (Phase 18.15)."""
        twin_row = await digital_twin_service.get_twin(db, organization_id)
        twin = digital_twin_service.serialize(twin_row) if twin_row else None

        if twin is None:
            await digital_twin_service.refresh(db, organization_id)
            await db.commit()
            twin_row = await digital_twin_service.get_twin(db, organization_id)
            twin = digital_twin_service.serialize(twin_row) if twin_row else None

        health = await health_service.latest(db, organization_id)
        if health is None:
            health = await health_service.compute(db, organization_id)
        predictions = await prediction_service.list(db, organization_id, status="active")
        recommendations = await recommendation_service.list(db, organization_id, status="active")
        simulations = await simulation_service.list(db, organization_id, limit=10)
        forecasts = await forecasting_service.list(db, organization_id, limit=20)
        optimizations = await optimization_service.list(db, organization_id, status="suggested", limit=10)
        decisions = await decision_service.list(db, organization_id, limit=10)

        return {
            "twin": twin,
            "health": health,
            "predictions": predictions,
            "recommendations": recommendations,
            "simulations": simulations,
            "forecasts": forecasts,
            "optimizations": optimizations,
            "decisions": decisions,
            "generated_at": utcnow().isoformat(),
        }

    async def brief(self, db: AsyncSession, organization_id: str) -> dict[str, Any]:
        """The autonomous morning brief — no manual report generation."""
        dash = await self.dashboard(db, organization_id)
        twin = dash["twin"] or {}
        health = dash["health"] or {}
        counts = twin.get("entity_counts", {})
        employees = counts.get("active_employees", counts.get("employees", 0) or 0)
        open_tasks = counts.get("open_tasks", 0) or 0
        projects = counts.get("active_projects", 0) or 0

        top_risks = [p for p in dash["predictions"] if p["level"] in ("high", "critical")][:3]
        top_recommendations = dash["recommendations"][:3]

        lines = []
        lines.append(f"Company health is **{health.get('status', 'unknown')}** at **{health.get('score', 0)}/100**.")
        lines.append(
            f"The organization model shows {employees} active employees, {projects} active projects, "
            f"{open_tasks} open tasks and {len(dash['forecasts'])} forecast dimensions."
        )
        if top_risks:
            lines.append("Top risks to watch: " + "; ".join(f"{r['title']} ({r['level']})" for r in top_risks) + ".")
        else:
            lines.append("No critical risks are currently predicted.")
        if top_recommendations:
            lines.append("Recommended focus: " + "; ".join(r["title"] for r in top_recommendations) + ".")
        if dash["simulations"]:
            latest = dash["simulations"][0]
            lines.append(f"Last simulation: **{latest['title']}** (risk {latest['results'].get('risk', 0)}/100).")
        return {
            "organization_id": organization_id,
            "generated_at": utcnow().isoformat(),
            "summary": "\n\n".join(lines),
            "highlights": {
                "health_score": health.get("score"),
                "health_status": health.get("status"),
                "employees": employees,
                "active_projects": projects,
                "open_tasks": open_tasks,
                "risk_count": len([p for p in dash["predictions"] if p["level"] in ("high", "critical")]),
                "recommendation_count": len(dash["recommendations"]),
            },
        }


executive_service = ExecutiveService()
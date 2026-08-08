"""Autonomous organization engine — the brain of the company.

Continuously observes employees, projects, tasks, meetings, documents,
knowledge, community, customers, vendors, learning, finance, automation and
executive decisions. Every pass: observe -> detect changes -> generate
insights -> update AI memory -> trigger recommendations.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.autonomy.awareness_engine import awareness_engine
from app.autonomy.health_engine import health_engine
from app.autonomy.prediction_engine import prediction_engine
from app.autonomy.recommendation_engine import recommendation_engine
from app.core.timeutils import utcnow
from app.events.publisher import publish_background_event
from app.models.company_state import CompanyState
from app.models.project import Project
from app.models.task import Task


class AutonomousOrganizationEngine:
    async def observe(
        self, db: AsyncSession, organization_id: str, *, commit: bool = False
    ) -> dict[str, Any]:
        """One full observation pass: state, changes, insights, memory, actions."""
        now = utcnow()
        previous = (
            await db.execute(
                select(CompanyState)
                .where(CompanyState.organization_id == organization_id)
                .order_by(CompanyState.snapshot_at.desc())
                .limit(1)
            )
        ).scalars().first()

        current = await awareness_engine.compute_state(db, organization_id)
        snapshot = CompanyState(
            organization_id=organization_id,
            state=current,
            score=self._activity_score(current),
            source="organization_engine",
            snapshot_at=now,
        )
        db.add(snapshot)
        await db.flush()

        changes = self._detect_changes(previous.state if previous else None, current)
        insights = self._generate_insights(current, changes)

        memory_recorded = 0
        for insight in insights[:3]:
            from app.memory.memory_service import memory_service

            await memory_service.record(
                db,
                organization_id=organization_id,
                memory_type="institutional",
                title=f"Insight: {insight['title'][:120]}",
                content=insight["detail"],
                tags=["insight", insight.get("domain", "organization")],
                importance="medium",
                source_event="organization.observed",
            )
            memory_recorded += 1

        predictions = await prediction_engine.generate(db, organization_id)
        recommendations = await recommendation_engine.generate(db, organization_id)
        health = await health_engine.refresh(db, organization_id)

        await publish_background_event(
            db, name="organization.observed", organization_id=organization_id,
            payload={
                "changes": len(changes), "insights": len(insights),
                "predictions": predictions["total"],
                "recommendations": recommendations["total"],
                "health_score": health["score"],
            },
        )
        if commit:
            await db.commit()
        return {
            "snapshot_id": snapshot.id,
            "score": snapshot.score,
            "changes": changes,
            "insights": insights,
            "memory_recorded": memory_recorded,
            "predictions": predictions["total"],
            "recommendations": recommendations["total"],
            "health_score": health["score"],
        }

    def _activity_score(self, state: dict[str, Any]) -> float:
        projects = state.get("projects", {})
        employees = state.get("employees", {})
        return round(
            (projects.get("active", 0) / max(projects.get("total", 1), 1)) * 60
            + (employees.get("online", 0) / max(employees.get("total", 1), 1)) * 40,
            1,
        )

    def _detect_changes(
        self, previous: dict[str, Any] | None, current: dict[str, Any]
    ) -> list[dict[str, Any]]:
        if not previous:
            return []
        changes: list[dict[str, Any]] = []
        prev_projects = previous.get("projects", {})
        cur_projects = current.get("projects", {})
        if cur_projects.get("total", 0) > prev_projects.get("total", 0):
            changes.append({"domain": "projects", "detail": "New project detected"})
        if cur_projects.get("active", 0) < prev_projects.get("active", 0):
            changes.append({"domain": "projects", "detail": "An active project was closed"})
        if current.get("tasks", {}).get("overdue", 0) > previous.get("tasks", {}).get("overdue", 0):
            changes.append({"domain": "tasks", "detail": "Overdue task count increased"})
        if current.get("employees", {}).get("total", 0) > previous.get("employees", {}).get("total", 0):
            changes.append({"domain": "employees", "detail": "Team grew (new employee hired)"})
        if current.get("budget", {}).get("usage_percent", 0) > previous.get("budget", {}).get("usage_percent", 0):
            changes.append({"domain": "finance", "detail": "Budget usage increased"})
        return changes

    def _generate_insights(
        self, current: dict[str, Any], changes: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        insights: list[dict[str, Any]] = []
        overdue = current.get("tasks", {}).get("overdue", 0)
        if overdue:
            insights.append({
                "domain": "tasks",
                "title": f"{overdue} overdue tasks need attention",
                "detail": "Prioritize clearing the overdue backlog to protect delivery dates.",
            })
        active = current.get("projects", {}).get("active", 0)
        total = current.get("projects", {}).get("total", 0)
        if total and active / total < 0.5:
            insights.append({
                "domain": "projects",
                "title": "More than half of projects are inactive",
                "detail": "Consider archiving stalled projects to reduce noise.",
            })
        usage = current.get("budget", {}).get("usage_percent", 0)
        if usage >= 80:
            insights.append({
                "domain": "finance",
                "title": "Budget usage is high",
                "detail": f"{usage}% of allocated budget is consumed; review before overruns.",
            })
        online = current.get("employees", {}).get("online", 0)
        emp_total = current.get("employees", {}).get("total", 0)
        if emp_total and online / max(emp_total, 1) < 0.3:
            insights.append({
                "domain": "employees",
                "title": "Low current online presence",
                "detail": "Most employees are offline right now; scheduling may matter.",
            })
        if not insights and changes:
            insights.append({
                "domain": "organization",
                "title": "Organization activity detected",
                "detail": f"{len(changes)} change(s) observed in the last pass.",
            })
        if not insights:
            insights.append({
                "domain": "organization",
                "title": "Organization is stable",
                "detail": "No significant changes detected in this pass.",
            })
        return insights


organization_engine = AutonomousOrganizationEngine()

"""Phase 8.14 — Predictive Analytics.

The forecasting layer predicts hiring needs, project completion, knowledge
growth, budget utilization signals, meeting effectiveness, learning progress,
innovation and turnover — always with a rationale and the factors used, so
executives can act BEFORE problems occur. Predictions persist to
``ai_predictions`` (shared with the Phase 7 prediction engine) and are
traceable to live data.
"""

import json
import logging
from datetime import timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.models.ai import AIPrediction
from app.models.employee import Employee
from app.models.executive import StrategicRisk
from app.models.knowledge import Document, WikiPage
from app.models.meeting import Meeting, MeetingActionItem
from app.models.project import Project
from app.models.task import Task
from app.models.workload import WorkloadSnapshot

logger = logging.getLogger("vcos.executive.forecasting")


def _level(score: float) -> str:
    if score >= 0.7:
        return "high"
    if score >= 0.4:
        return "medium"
    return "low"


class ForecastingService:
    async def predict_all(self, db: AsyncSession, *, organization_id: str, persist: bool = True) -> list[dict[str, Any]]:
        predictions: list[dict[str, Any]] = []
        predictions.extend(await self._project_completion(db, organization_id=organization_id))
        predictions.extend(await self._hiring_need(db, organization_id=organization_id))
        predictions.extend(await self._turnover(db, organization_id=organization_id))
        predictions.extend(await self._knowledge_growth(db, organization_id=organization_id))
        predictions.extend(await self._meeting_effectiveness(db, organization_id=organization_id))
        predictions.extend(await self._innovation_momentum(db, organization_id=organization_id))
        predictions.sort(key=lambda p: p["score"], reverse=True)
        if persist:
            await self.persist(db, organization_id=organization_id, predictions=predictions)
        return predictions

    def _build(
        self, *, organization_id: str, metric: str, score: float, rationale: str,
        factors: dict[str, Any], subject_type: str = "organization", subject_id: str | None = None,
    ) -> dict[str, Any]:
        return {
            "organization_id": organization_id,
            "subject_type": subject_type,
            "subject_id": subject_id,
            "metric": metric,
            "score": round(score, 2),
            "level": _level(score),
            "rationale": rationale,
            "factors": factors,
        }

    async def _project_completion(self, db: AsyncSession, *, organization_id: str) -> list[dict[str, Any]]:
        projects = (await db.execute(
            select(Project).where(
                Project.organization_id == organization_id,
                Project.status.in_(("active", "draft", "paused")),
            )
        )).scalars().all()
        results = []
        for p in projects[:10]:
            total = (
                await db.execute(select(func.count(Task.id)).where(
                    Task.organization_id == organization_id, Task.project_id == p.id
                ))
            ).scalar() or 0
            completed = (
                await db.execute(select(func.count(Task.id)).where(
                    Task.organization_id == organization_id, Task.project_id == p.id, Task.status == "completed"
                ))
            ).scalar() or 0
            overdue = (
                await db.execute(select(func.count(Task.id)).where(
                    Task.organization_id == organization_id,
                    Task.project_id == p.id,
                    Task.due_date.isnot(None),
                    Task.due_date < utcnow().date(),
                    Task.status.notin_(("completed", "archived")),
                ))
            ).scalar() or 0
            blocked = (
                await db.execute(select(func.count(Task.id)).where(
                    Task.organization_id == organization_id, Task.project_id == p.id, Task.status == "blocked"
                ))
            ).scalar() or 0
            progress = (completed / total * 100) if total else float(p.progress or 0)
            miss_score = 0.2
            factors = {"progress": round(progress, 1), "total_tasks": total, "overdue": overdue, "blocked": blocked}
            if overdue:
                miss_score += min(0.35, overdue * 0.05)
            if blocked:
                miss_score += min(0.25, blocked * 0.05)
            if progress < 30 and total > 5:
                miss_score += 0.15
            if p.health == "critical":
                miss_score += 0.1
            miss_score = min(0.95, miss_score)
            results.append(self._build(
                organization_id=organization_id,
                metric="project_miss",
                score=miss_score,
                rationale=f"Project '{p.name}' is at {progress:.0f}% progress with {overdue} overdue and {blocked} blocked task(s).",
                factors=factors,
                subject_type="project",
                subject_id=p.id,
            ))
        return results

    async def _hiring_need(self, db: AsyncSession, *, organization_id: str) -> list[dict[str, Any]]:
        week_ago = utcnow() - timedelta(days=7)
        overloaded = (
            await db.execute(select(func.count(func.distinct(WorkloadSnapshot.employee_id))).where(
                WorkloadSnapshot.organization_id == organization_id,
                WorkloadSnapshot.period_start >= week_ago,
                WorkloadSnapshot.is_overloaded.is_(True),
            ))
        ).scalar() or 0
        open_tasks = (
            await db.execute(select(func.count(Task.id)).where(
                Task.organization_id == organization_id,
                Task.status.notin_(("completed", "archived")),
            ))
        ).scalar() or 0
        dependency = (
            await db.execute(select(func.count(StrategicRisk.id)).where(
                StrategicRisk.organization_id == organization_id,
                StrategicRisk.status == "open",
                StrategicRisk.kind.in_(("key_dependency", "overload")),
            ))
        ).scalar() or 0
        score = min(0.95, 0.15 + overloaded * 0.12 + (open_tasks / 500) + dependency * 0.05)
        return [self._build(
            organization_id=organization_id,
            metric="hiring_need",
            score=score,
            rationale=f"{overloaded} overloaded employee(s) and {open_tasks} open tasks signal a hiring need in the next quarter.",
            factors={"overloaded_employees": overloaded, "open_tasks": open_tasks, "dependency_risks": dependency},
        )]

    async def _turnover(self, db: AsyncSession, *, organization_id: str) -> list[dict[str, Any]]:
        month_ago = utcnow() - timedelta(days=30)
        employees = (await db.execute(
            select(Employee).where(Employee.organization_id == organization_id, Employee.status == "active")
        )).scalars().all()
        results = []
        for e in employees:
            active_tasks = (
                await db.execute(select(func.count(Task.id)).where(
                    Task.organization_id == organization_id,
                    Task.assignee_id == e.id,
                    Task.status.in_(("in_progress", "review", "todo")),
                ))
            ).scalar() or 0
            score = 0.05
            factors: dict[str, Any] = {"active_tasks": active_tasks}
            if active_tasks >= 10:
                score += 0.2
                factors["overloaded"] = True
            if e.expertise_score and e.expertise_score < 5:
                score += 0.05
            if score >= 0.2:
                name = e.display_name or f"{e.first_name} {e.last_name or ''}".strip()
                results.append(self._build(
                    organization_id=organization_id,
                    metric="turnover_risk",
                    score=score,
                    rationale=f"{name} carries {active_tasks} active tasks — sustained overload raises attrition risk.",
                    factors=factors,
                    subject_type="employee",
                    subject_id=e.id,
                ))
        return results

    async def _knowledge_growth(self, db: AsyncSession, *, organization_id: str) -> list[dict[str, Any]]:
        now = utcnow()
        month_ago = now - timedelta(days=30)
        total = 0
        recent = 0
        for model in (Document, WikiPage):
            total += (
                await db.execute(select(func.count(model.id)).where(model.organization_id == organization_id))
            ).scalar() or 0
            recent += (
                await db.execute(select(func.count(model.id)).where(
                    model.organization_id == organization_id, model.created_at >= month_ago
                ))
            ).scalar() or 0
        rate = recent if recent else 0
        projected = round(rate * 3, 0)  # quarterly projection from monthly rate
        score = min(0.9, 0.1 + rate * 0.1)
        return [self._build(
            organization_id=organization_id,
            metric="knowledge_growth",
            score=score,
            rationale=f"{recent} knowledge items published in the last 30 days; projected ~{projected} next quarter.",
            factors={"total_items": total, "recent_items": recent, "projected_next_quarter": projected},
        )]

    async def _meeting_effectiveness(self, db: AsyncSession, *, organization_id: str) -> list[dict[str, Any]]:
        now = utcnow()
        week_ago = now - timedelta(days=7)
        meetings = (await db.execute(
            select(Meeting).where(
                Meeting.organization_id == organization_id,
                Meeting.status == "completed",
                Meeting.end_at >= week_ago,
            )
        )).scalars().all()
        effective = 0
        for m in meetings:
            has_summary = bool(m.ai_summary or m.transcript_summary)
            actions = (
                await db.execute(select(func.count(MeetingActionItem.id)).where(
                    MeetingActionItem.meeting_id == m.id
                ))
            ).scalar() or 0
            if has_summary or actions > 0:
                effective += 1
        ratio = (effective / len(meetings)) if meetings else 1.0
        score = round(max(0.05, min(0.95, 1 - ratio * 0.8)), 2)
        return [self._build(
            organization_id=organization_id,
            metric="meeting_effectiveness",
            score=score,
            rationale=f"{effective}/{len(meetings)} completed meetings this week produced summaries or action items."
            if meetings else "No completed meetings this week to evaluate.",
            factors={"meetings_completed": len(meetings), "effective": effective},
        )]

    async def _innovation_momentum(self, db: AsyncSession, *, organization_id: str) -> list[dict[str, Any]]:
        from app.models.communication import InnovationIdea

        now = utcnow()
        month_ago = now - timedelta(days=30)
        recent = (
            await db.execute(select(func.count(InnovationIdea.id)).where(
                InnovationIdea.organization_id == organization_id, InnovationIdea.created_at >= month_ago
            ))
        ).scalar() or 0
        score = min(0.9, recent * 0.15)
        return [self._build(
            organization_id=organization_id,
            metric="innovation_momentum",
            score=score,
            rationale=f"{recent} innovation idea(s) submitted in the last 30 days.",
            factors={"ideas_last_30d": recent},
        )]

    async def persist(self, db: AsyncSession, *, organization_id: str, predictions: list[dict[str, Any]]) -> int:
        existing = (await db.execute(
            select(AIPrediction).where(
                AIPrediction.organization_id == organization_id,
                AIPrediction.subject_type == "organization",
                AIPrediction.metric.in_(
                    ("project_miss", "hiring_need", "turnover_risk", "knowledge_growth", "meeting_effectiveness", "innovation_momentum")
                ),
            )
        )).scalars().all()
        existing_by_key = {(p.metric, p.subject_id or ""): p for p in existing}
        created = 0
        for p in predictions:
            key = (p["metric"], p.get("subject_id") or "")
            row = existing_by_key.get(key)
            if row is not None:
                row.score = p["score"]
                row.level = p["level"]
                row.rationale = p["rationale"]
                row.factors_json = json.dumps(p["factors"])
                continue
            db.add(AIPrediction(
                organization_id=organization_id,
                subject_type=p["subject_type"],
                subject_id=p.get("subject_id"),
                metric=p["metric"],
                score=p["score"],
                level=p["level"],
                rationale=p["rationale"],
                factors_json=json.dumps(p["factors"]),
            ))
            created += 1
        return created


forecasting_service = ForecastingService()

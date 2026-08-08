"""Phase 8.1 — Executive Dashboard (CEO homepage).

One screen for leadership: instead of charts everywhere, AI summarizes the
organization — company health, department health, project health, strategic
goals, risks, predictions, recommendations, innovation, knowledge, growth
trends, executive calendar and recent decisions. Everything is traceable to
live organizational data.
"""

import logging
from datetime import timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.executive.digital_twin import digital_twin
from app.executive.forecasting import forecasting_service
from app.executive.health_engine import health_engine
from app.executive.recommendation_engine import recommendation_engine
from app.executive.reporting import reporting_service
from app.executive.risk_engine import risk_engine
from app.executive.timeline import organization_timeline
from app.models.executive import ExecutiveRecommendation, StrategicRisk
from app.models.knowledge import Decision
from app.models.meeting import Meeting
from app.models.organization import Organization
from app.models.project import Project

logger = logging.getLogger("vcos.executive.dashboard")


class ExecutiveDashboardService:
    async def get(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        refresh: bool = False,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        org = await db.get(Organization, organization_id)
        org_name = org.name if org else "Organization"

        if refresh:
            await health_engine.compute_company_health(db, organization_id=organization_id, persist=True)
            risks = await risk_engine.detect_all(db, organization_id=organization_id)
            await risk_engine.persist(db, organization_id=organization_id, risks=risks)
            await recommendation_engine.generate(db, organization_id=organization_id, persist=True)
            await forecasting_service.predict_all(db, organization_id=organization_id, persist=True)

        health = await health_engine.compute_company_health(db, organization_id=organization_id, persist=False)
        risks = (await db.execute(
            select(StrategicRisk).where(
                StrategicRisk.organization_id == organization_id, StrategicRisk.status == "open"
            ).order_by(StrategicRisk.score.desc())
        )).scalars().all()
        recommendations = (await db.execute(
            select(ExecutiveRecommendation).where(
                ExecutiveRecommendation.organization_id == organization_id,
                ExecutiveRecommendation.status == "active",
            ).order_by(ExecutiveRecommendation.confidence.desc())
        )).scalars().all()

        twin_payload = await digital_twin.describe(db, organization_id=organization_id)
        departments_health = await health_engine.departments_health(db, organization_id=organization_id)

        now = utcnow()
        upcoming_meetings = (await db.execute(
            select(Meeting).where(
                Meeting.organization_id == organization_id,
                Meeting.start_at >= now,
                Meeting.status != "cancelled",
            ).order_by(Meeting.start_at.asc()).limit(10)
        )).scalars().all()
        recent_decisions = (await db.execute(
            select(Decision).where(Decision.organization_id == organization_id)
            .order_by(Decision.created_at.desc()).limit(8)
        )).scalars().all()

        projects = (await db.execute(
            select(Project).where(
                Project.organization_id == organization_id,
                Project.status.notin_(("completed", "cancelled", "archived")),
            )
        )).scalars().all()
        project_healths = []
        for p in projects[:30]:
            try:
                project_healths.append({
                    "project_id": p.id,
                    "name": p.name,
                    "health": (await health_engine.project_health(
                        db, organization_id=organization_id, project_id=p.id
                    ))["health"],
                    "progress": p.progress,
                    "status": p.status,
                })
            except Exception as exc:  # pragma: no cover
                logger.warning("project health failed for %s: %s", p.id, exc)
        project_healths.sort(key=lambda x: x["health"])

        critical_risks = [r for r in risks if r.level in ("high", "critical")]
        high_recs = [r for r in recommendations if r.impact == "high"]

        summary = self._compose_summary(
            org_name=org_name, health=health, risks=risks,
            recommendations=recommendations, twin=twin_payload,
        )

        timeline = await organization_timeline.get(db, organization_id=organization_id, limit=12)

        return {
            "organization": {"id": organization_id, "name": org_name},
            "generated_at": now.isoformat(),
            "health": health,
            "summary": summary,
            "attention": {
                "critical_risks": len(critical_risks),
                "active_recommendations": len(recommendations),
                "overdue_tasks": health["counts"]["tasks_overdue"],
                "overloaded_employees": health["counts"]["overloaded_employees"],
                "knowledge_total": health["counts"]["knowledge_total"],
            },
            "departments_health": departments_health,
            "projects_health": project_healths[:12],
            "risks": [
                self._risk_payload(r)
                for r in risks[:10]
            ],
            "recommendations": [
                {
                    "id": r.id,
                    "kind": r.kind,
                    "title": r.title,
                    "rationale": r.rationale,
                    "expected_outcome": r.expected_outcome,
                    "confidence": r.confidence,
                    "impact": r.impact,
                    "status": r.status,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
                for r in recommendations[:8]
            ],
            "digital_twin": twin_payload["entity_counts"],
            "executive_calendar": [
                {
                    "id": m.id,
                    "title": m.title,
                    "start_at": m.start_at.isoformat() if m.start_at else None,
                    "meeting_type": m.meeting_type,
                    "status": m.status,
                }
                for m in upcoming_meetings
            ],
            "recent_decisions": [
                {
                    "id": d.id,
                    "title": d.title,
                    "status": getattr(d, "status", ""),
                    "created_at": d.created_at.isoformat() if d.created_at else None,
                }
                for d in recent_decisions
            ],
            "recent_activity": timeline["entries"],
            "strategy": twin_payload["twin"]["strategy"],
        }

    def _compose_summary(
        self, *, org_name: str, health: dict[str, Any],
        risks: list[Any], recommendations: list[Any], twin: dict[str, Any],
    ) -> str:
        counts = twin["entity_counts"]
        lines = [f"{org_name} today: company health {health['score']:.0f}/100 ({health['status']})."]
        lines.append(
            f"{counts['employees_active']} active employees across {counts['departments']} departments, "
            f"{counts['projects_active']} active projects, {counts['tasks_open']} open tasks "
            f"({counts['tasks_overdue']} overdue), {counts['meetings']} meetings on record and "
            f"{counts['knowledge']} knowledge items."
        )
        critical = [r for r in risks if r.level in ("high", "critical")]
        if critical:
            lines.append(f"Needs attention: {len(critical)} strategic risk(s) — " + "; ".join(r.title for r in critical[:3]) + ".")
        elif risks:
            lines.append(f"Risk posture is calm: {len(risks)} open risk(s), none critical.")
        else:
            lines.append("No open strategic risks detected.")
        if recommendations:
            top = recommendations[0]
            lines.append(
                f"Top recommendation: {top.title} (confidence {top.confidence:.0%}). "
                f"Expected outcome: {top.expected_outcome}"
            )
        else:
            lines.append("No active recommendations right now.")
        return " ".join(lines)

    @staticmethod
    def _risk_payload(r: Any) -> dict[str, Any]:
        import json as _json

        def _load(v):
            if not v:
                return []
            try:
                return _json.loads(v)
            except (_json.JSONDecodeError, TypeError):
                return []

        return {
            "id": r.id,
            "kind": r.kind,
            "title": r.title,
            "description": r.description,
            "probability": r.probability,
            "impact": r.impact,
            "score": r.score,
            "level": r.level,
            "subject_type": r.subject_type,
            "subject_id": r.subject_id,
            "subject_name": r.subject_name,
            "affected_teams": _load(r.affected_teams_json),
            "recommended_actions": _load(r.recommended_actions_json),
            "evidence": _load(r.evidence_json),
            "status": r.status,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }


executive_dashboard = ExecutiveDashboardService()

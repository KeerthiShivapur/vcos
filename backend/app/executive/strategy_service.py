"""Phase 8.4/8.15/8.16 — Strategic Goal Intelligence & Executive AI Assistant.

The strategy layer tracks the company's strategic goals (vision -> goals ->
objectives) and answers executives' natural questions — "summarize this
week", "show biggest risks", "who needs help?", "prepare board meeting",
"generate quarterly report" — with evidence, using the companion's rules
engine plus the gateway LLM when configured.
"""

import json
import logging
from datetime import timedelta
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.executive.dashboard import executive_dashboard
from app.executive.forecasting import forecasting_service
from app.executive.health_engine import health_engine
from app.executive.recommendation_engine import recommendation_engine
from app.executive.reporting import reporting_service
from app.executive.risk_engine import risk_engine
from app.executive.simulation_engine import simulation_engine
from app.models.executive import StrategicGoal
from app.models.organization import Organization

logger = logging.getLogger("vcos.executive.strategy")

GOAL_FOCUSES = ["growth", "retention", "innovation", "efficiency", "expansion", "learning"]


class StrategyService:
    async def list_goals(
        self, db: AsyncSession, *, organization_id: str, focus: str | None = None, status: str | None = None
    ) -> dict[str, Any]:
        query = select(StrategicGoal).where(StrategicGoal.organization_id == organization_id)
        if focus:
            query = query.where(StrategicGoal.focus == focus)
        if status:
            query = query.where(StrategicGoal.status == status)
        rows = (await db.execute(query.order_by(StrategicGoal.created_at.desc()))).scalars().all()
        return {
            "total": len(rows),
            "goals": [
                {
                    "id": g.id,
                    "name": g.name,
                    "description": g.description,
                    "timeframe": g.timeframe,
                    "status": g.status,
                    "progress": g.progress,
                    "priority": g.priority,
                    "focus": g.focus,
                    "created_at": g.created_at.isoformat() if g.created_at else None,
                }
                for g in rows
            ],
        }

    async def create_goal(
        self, db: AsyncSession, *, organization_id: str, payload: dict[str, Any], owner_id: str | None = None
    ) -> dict[str, Any]:
        focus = payload.get("focus", "growth")
        if focus not in GOAL_FOCUSES:
            focus = "growth"
        goal = StrategicGoal(
            organization_id=organization_id,
            name=payload["name"],
            description=payload.get("description"),
            timeframe=payload.get("timeframe", "quarter"),
            status=payload.get("status", "planned"),
            progress=float(payload.get("progress", 0) or 0),
            priority=payload.get("priority", "medium"),
            focus=focus,
            links_json=json.dumps(payload.get("links", {})),
            owner_id=owner_id,
        )
        db.add(goal)
        await db.flush()
        return {
            "id": goal.id,
            "name": goal.name,
            "timeframe": goal.timeframe,
            "status": goal.status,
            "progress": goal.progress,
            "focus": goal.focus,
        }

    async def update_goal(
        self, db: AsyncSession, *, organization_id: str, goal_id: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        goal = await db.get(StrategicGoal, goal_id)
        if goal is None or goal.organization_id != organization_id:
            raise ValueError("Strategic goal not found")
        for field in ("name", "description", "timeframe", "status", "priority", "focus"):
            if field in payload and payload[field] is not None:
                setattr(goal, field, payload[field])
        if "progress" in payload:
            goal.progress = float(payload["progress"] or 0)
        return {
            "id": goal.id,
            "name": goal.name,
            "timeframe": goal.timeframe,
            "status": goal.status,
            "progress": goal.progress,
            "priority": goal.priority,
            "focus": goal.focus,
        }

    async def plan(self, db: AsyncSession, *, organization_id: str, horizon: str = "quarter") -> dict[str, Any]:
        """Phase 8.15 — AI drafts a strategy plan from live data."""
        health = await health_engine.compute_company_health(db, organization_id=organization_id, persist=False)
        risks = await risk_engine.detect_all(db, organization_id=organization_id)
        recommendations = await recommendation_engine.generate(
            db, organization_id=organization_id, persist=False
        )
        predictions = await forecasting_service.predict_all(
            db, organization_id=organization_id, persist=False
        )
        high_risks = [r for r in risks if r["level"] in ("high", "critical")]
        top_recs = recommendations[:4]
        priorities = [r["title"] for r in top_recs]
        focus_areas = list({
            r.get("subject_type", "organization")
            for r in high_risks[:3]
        } or ["organization"])
        return {
            "horizon": horizon,
            "company_health": health["score"],
            "status": health["status"],
            "priorities": priorities or ["Protect delivery velocity and close open risks"],
            "focus_areas": focus_areas,
            "initiatives": [
                {
                    "title": p,
                    "why": recommendations[i]["rationale"] if i < len(recommendations) else "",
                    "evidence": recommendations[i]["evidence"] if i < len(recommendations) else {},
                }
                for i, p in enumerate(priorities)
            ],
            "predictions": [
                {"metric": p["metric"], "level": p["level"], "rationale": p["rationale"]}
                for p in predictions[:5]
            ],
            "generated_at": utcnow().isoformat(),
        }

    async def ask(self, db: AsyncSession, *, organization_id: str, user_id: str, question: str) -> dict[str, Any]:
        """Phase 8.16 — Executive AI assistant: answer with evidence."""
        q = question.strip().lower()
        org = await db.get(Organization, organization_id)
        org_name = org.name if org else "Organization"

        if "board" in q and ("meeting" in q or "report" in q or "prepare" in q):
            report = await reporting_service.generate(
                db, organization_id=organization_id, report_type="board", user_id=user_id
            )
            return self._answer(
                question, f"Board meeting pack for {org_name} is ready. Here are the key numbers: "
                + json.dumps(report["stats"]),
                {"report_type": "board", "stats": report["stats"]}, "report",
            )

        if "quarterly" in q or "quarter report" in q:
            report = await reporting_service.generate(
                db, organization_id=organization_id, report_type="quarterly", user_id=user_id
            )
            return self._answer(
                question, f"Quarterly report generated for {org_name}. Top numbers: "
                + json.dumps(report["stats"]),
                {"report_type": "quarterly", "stats": report["stats"]}, "report",
            )

        if "summar" in q and ("week" in q or "month" in q):
            period = "monthly" if "month" in q else "weekly"
            report = await reporting_service.generate(
                db, organization_id=organization_id, report_type=period, user_id=user_id
            )
            return self._answer(
                question,
                f"This {period.replace('ly', '').replace('l', '')} period for {org_name}: "
                f"{report['stats']['tasks_completed']} tasks completed, {report['stats']['meetings']} meetings, "
                f"{report['stats']['knowledge_published']} knowledge items, "
                f"{report['stats']['open_strategic_risks']} open strategic risks. Full report: {report['title']}.",
                {"stats": report["stats"]}, "summary",
            )

        if "risk" in q and ("biggest" in q or "show" in q or "list" in q or "what" in q):
            risks = await risk_engine.detect_all(db, organization_id=organization_id)
            top = risks[:5]
            lines = [f"Biggest risks for {org_name}:"]
            for r in top:
                lines.append(f"- {r['title']} ({r['level']}, score {r['score']:.2f}). Recommended: {'; '.join(r['recommended_actions'][:2])}.")
            if not top:
                lines.append("- No risks detected right now.")
            return self._answer(question, "\n".join(lines), {"risks": top}, "risks")

        if "health" in q or "how is the company" in q:
            health = await health_engine.compute_company_health(db, organization_id=organization_id, persist=False)
            weakest = sorted(health["breakdown"].items(), key=lambda x: x[1])[:3]
            return self._answer(
                question,
                f"{org_name} health is {health['score']:.0f}/100 ({health['status']}). "
                f"Weakest dimensions: " + ", ".join(f"{k.replace('_', ' ')} ({v:.0f})" for k, v in weakest) + ".",
                {"score": health["score"], "breakdown": health["breakdown"]}, "health",
            )

        if "help" in q and ("who" in q or "needs" in q):
            health = await health_engine.compute_company_health(db, organization_id=organization_id, persist=False)
            overloaded = health["counts"]["overloaded_employees"]
            overdue = health["counts"]["tasks_overdue"]
            answer = (
                f"{overloaded} employee(s) are flagged overloaded and {overdue} tasks are overdue. "
                f"Recommend checking in with overloaded team members and reprioritizing overdue work."
            )
            return self._answer(question, answer, {"overloaded": overloaded, "overdue": overdue}, "people")

        if "contributor" in q or "top performer" in q:
            from app.models.employee import Employee
            from app.models.task import Task

            rows = (await db.execute(
                select(Task.assignee_id, Task.organization_id, Employee.first_name, Employee.last_name, Employee.display_name)
                .join(Employee, Employee.id == Task.assignee_id)
                .where(Task.organization_id == organization_id, Task.status == "completed")
            )).all()
            counts: dict[str, dict[str, Any]] = {}
            for assignee_id, _org, first, last, display in rows:
                if not assignee_id:
                    continue
                name = display or f"{first} {last or ''}".strip()
                counts.setdefault(assignee_id, {"name": name, "completed": 0})["completed"] += 1
            top = sorted(counts.values(), key=lambda x: x["completed"], reverse=True)[:5]
            answer = "Top contributors by completed tasks: " + ", ".join(
                f"{c['name']} ({c['completed']})" for c in top
            ) if top else "No completed tasks to rank yet."
            return self._answer(question, answer, {"top": top}, "people")

        if "waste" in q or "meeting" in q and "too much" in q:
            from app.models.meeting import Meeting

            week_ago = utcnow() - timedelta(days=7)
            count = (
                await db.execute(select(func.count(Meeting.id)).where(
                    Meeting.organization_id == organization_id,
                    Meeting.start_at >= week_ago,
                    Meeting.status != "cancelled",
                ))
            ).scalar() or 0
            return self._answer(
                question,
                f"{count} meetings were held in the last 7 days. If 30% were replaced by async updates, "
                f"the team would recover roughly {round(count * 0.3)} hours of focus time per week.",
                {"meetings_7d": count}, "time",
            )

        if "simulate" in q or "what if" in q or "happens if" in q:
            scenario = self._scenario_from_question(q)
            if scenario:
                result = await simulation_engine.simulate(
                    db, organization_id=organization_id, scenario=scenario,
                    params={"count": 3, "weeks": 2, "percent": 30}, user_id=user_id, persist=True,
                )
                return self._answer(
                    question,
                    f"Simulation '{result['title']}': " + json.dumps(result["results"]) + ". "
                    f"Assumptions: " + "; ".join(result["assumptions"]),
                    {"results": result["results"], "assumptions": result["assumptions"]}, "simulation",
                )

        if "recommend" in q or "what should i do" in q:
            recommendations = await recommendation_engine.generate(
                db, organization_id=organization_id, persist=False
            )
            top = recommendations[:3]
            lines = ["My recommendations, in priority order:"]
            for r in top:
                lines.append(f"- {r['title']} (confidence {r['confidence']:.0%}). Why: {r['rationale']}")
            return self._answer(question, "\n".join(lines), {"recommendations": top}, "recommendations")

        if "simulation" in q or "scenario" in q:
            return self._answer(
                question,
                "I can simulate: hire engineers, delay a release, lose a specialist, sales increase, "
                "merge teams, expand to a new region, or reduce meetings. Try 'simulate hiring 5 engineers'.",
                {"scenarios": simulation_engine.SCENARIOS}, "help",
            )

        health = await health_engine.compute_company_health(db, organization_id=organization_id, persist=False)
        return self._answer(
            question,
            f"Here's where {org_name} stands: health {health['score']:.0f}/100 ({health['status']}), "
            f"{health['counts']['active_projects']} active projects, {health['counts']['tasks_overdue']} overdue tasks. "
            "Ask me about risks, health, top contributors, meeting time, simulations or a board/quarterly report.",
            {"health": health["score"]}, "general",
        )

    @staticmethod
    def _scenario_from_question(q: str) -> Optional[str]:
        if "hire" in q and ("engineer" in q or "developer" in q):
            return "hire_engineers"
        if "delay" in q and "release" in q:
            return "delay_release"
        if "lose" in q and ("architect" in q or "specialist" in q or "engineer" in q):
            return "lose_specialist"
        if "sales" in q and "increase" in q:
            return "sales_increase"
        if "merge" in q and ("team" in q or "teams" in q):
            return "merge_teams"
        if "expand" in q or "open" in q and ("office" in q or "region" in q):
            return "expand"
        if "reduce" in q and "meeting" in q:
            return "reduce_meetings"
        return None

    @staticmethod
    def _answer(question: str, answer: str, evidence: dict[str, Any], kind: str) -> dict[str, Any]:
        return {
            "answer": answer,
            "question": question,
            "kind": kind,
            "source": "rules",
            "evidence": evidence,
        }


strategy_service = StrategyService()

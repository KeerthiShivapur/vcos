"""Enterprise reasoning engine — AI doesn't retrieve, AI reasons.

Given a question ("Why is Project Apollo delayed?"), the engine gathers
evidence across tasks, meetings, risks, people, dependencies, knowledge,
calendar, approvals, customers, budgets, learning and the organization graph,
then explains root causes with a connected explanation.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.models.customer import Customer
from app.models.employee import Employee
from app.models.knowledge import Document
from app.models.meeting import Meeting
from app.models.project import Project
from app.models.task import Task
from app.models.workflow import WorkflowApproval

INTENTS = (
    "why_delayed", "who_knows", "summarize", "recommend_next", "what_to_learn",
    "skill_gap", "explain_health", "predict_quarter", "strategic_risk",
    "customer_trends", "org_knowledge",
)


class ReasoningEngine:
    async def ask(
        self, db: AsyncSession, organization_id: str, question: str
    ) -> dict[str, Any]:
        lowered = question.lower()
        intent = self._classify(lowered)
        now = utcnow()
        evidence: dict[str, Any] = {}

        if intent in ("why_delayed", "missed_deadlines", "why_is_my_team_slowing"):
            evidence = await self._delay_evidence(db, organization_id, lowered, now)
        elif intent in ("who_knows", "who_should_help"):
            evidence = await self._expertise_evidence(db, organization_id, lowered)
        elif intent in ("explain_health", "company_health", "health"):
            evidence = await self._health_evidence(db, organization_id)
        elif intent in ("summarize", "my_organization", "company"):
            evidence = await self._summary_evidence(db, organization_id, lowered, now)
        elif intent == "what_to_learn":
            evidence = await self._learning_evidence(db, organization_id, lowered)
        elif intent in ("predict_quarter", "next_quarter", "predict"):
            evidence = await self._prediction_evidence(db, organization_id)
        elif intent in ("customer_trends", "customers"):
            evidence = await self._customer_evidence(db, organization_id)
        elif intent in ("strategic_risk", "risks"):
            evidence = await self._risk_evidence(db, organization_id, now)
        else:
            evidence = await self._summary_evidence(db, organization_id, lowered, now)

        conclusion = self._conclude(intent, evidence)
        return {
            "question": question,
            "intent": intent,
            "evidence": evidence,
            "root_causes": evidence.get("root_causes", []),
            "conclusion": conclusion,
            "recommendations": evidence.get("recommendations", []),
            "answered_at": now.isoformat(),
        }

    def _classify(self, lowered: str) -> str:
        if any(w in lowered for w in ("delayed", "delay", "late", "slowing", "blocked", "why")):
            return "why_delayed"
        if any(w in lowered for w in ("who knows", "who should", "expert", "help me", "knows this")):
            return "who_knows"
        if any(w in lowered for w in ("health", "how is the company")):
            return "explain_health"
        if any(w in lowered for w in ("predict", "next quarter", "forecast", "future")):
            return "predict_quarter"
        if any(w in lowered for w in ("customers", "customer trend", "churn")):
            return "customer_trends"
        if any(w in lowered for w in ("risk", "risk", "threat")):
            return "strategic_risk"
        if any(w in lowered for w in ("learn", "skill", "training", "what should i")):
            return "what_to_learn"
        if any(w in lowered for w in ("summarize", "my organization", "overview", "company")):
            return "summarize"
        return "summarize"

    async def _delay_evidence(
        self, db: AsyncSession, organization_id: str, question: str, now: Any
    ) -> dict[str, Any]:
        project = None
        for token in question.replace("?", "").split():
            if token.lower() in ("why", "is", "delayed", "the", "project", "my", "team", "slowing", "what"):
                continue
            candidate = (
                await db.execute(
                    select(Project).where(
                        Project.organization_id == organization_id,
                        Project.name.ilike(f"%{token[:30]}%"),
                    ).limit(1)
                )
            ).scalars().first()
            if candidate is not None:
                project = candidate
                break
        if project is None:
            project = (
                await db.execute(
                    select(Project)
                    .where(Project.organization_id == organization_id)
                    .order_by(Project.updated_at.desc())
                    .limit(1)
                )
            ).scalars().first()
        if project is None:
            return {"root_causes": [], "recommendations": [], "notes": ["No projects found"]}

        tasks = (
            await db.execute(
                select(Task).where(
                    Task.organization_id == organization_id, Task.project_id == project.id
                )
            )
        ).scalars().all()
        overdue = [t for t in tasks if t.due_date is not None and t.due_date < now
                   and t.status not in ("done", "completed", "cancelled")]
        blocked = [t for t in tasks if t.status == "blocked"]
        in_progress = [t for t in tasks if t.status in ("todo", "in_progress")]
        heavy_assignees = {}
        for t in in_progress:
            if t.assignee_id:
                heavy_assignees[t.assignee_id] = heavy_assignees.get(t.assignee_id, 0) + 1
        overloaded = {k: v for k, v in heavy_assignees.items() if v >= 6}

        meetings = (
            await db.execute(
                select(Meeting).where(
                    Meeting.organization_id == organization_id,
                    Meeting.project_id == project.id,
                ).limit(20)
            )
        ).scalars().all()
        docs = (
            await db.execute(
                select(func.count(Document.id)).where(
                    Document.organization_id == organization_id, Document.project_id == project.id
                )
            )
        ).scalar() or 0
        pending_approvals = (
            await db.execute(
                select(func.count(WorkflowApproval.id)).where(
                    WorkflowApproval.organization_id == organization_id,
                    WorkflowApproval.status == "pending",
                )
            )
        ).scalar() or 0

        root_causes: list[str] = []
        if overdue:
            root_causes.append(f"{len(overdue)} overdue tasks on this project")
        if blocked:
            root_causes.append(f"{len(blocked)} blocked task(s) stalling progress")
        if overloaded:
            root_causes.append(f"{len(overloaded)} assignee(s) carrying 6+ open tasks")
        if not meetings:
            root_causes.append("Few or no meetings recorded for the project (coordination gap)")
        if docs == 0:
            root_causes.append("No documentation exists for the project (knowledge gap)")
        if pending_approvals:
            root_causes.append(f"{pending_approvals} approval(s) pending organization-wide")
        if not root_causes:
            root_causes.append("No strong delay signals; schedule may be optimistic")

        recommendations: list[str] = []
        if overloaded:
            recommendations.append("Reassign work from overloaded assignees")
        if blocked:
            recommendations.append("Unblock blocked tasks by resolving dependencies")
        if docs == 0:
            recommendations.append("Generate missing project documentation")
        if pending_approvals:
            recommendations.append("Escalate pending approvals")
        if not recommendations:
            recommendations.append("Re-baseline the project plan with realistic dates")

        return {
            "project": {"id": project.id, "name": project.name},
            "tasks": {"total": len(tasks), "overdue": len(overdue), "blocked": len(blocked)},
            "root_causes": root_causes,
            "recommendations": recommendations,
        }

    async def _expertise_evidence(
        self, db: AsyncSession, organization_id: str, question: str
    ) -> dict[str, Any]:
        employees = (
            await db.execute(
                select(Employee).where(Employee.organization_id == organization_id).limit(500)
            )
        ).scalars().all()
        skills = sorted(question.replace("who", "").replace("knows", "").replace("?", "").split())
        matches: list[dict[str, Any]] = []
        for emp in employees:
            emp_skills = set((getattr(emp, "skills", None) or []) + (getattr(emp, "skills_list", None) or []))
            if isinstance(emp_skills, list):
                emp_skills = set(map(str, emp_skills))
            score = 0
            for token in skills:
                if token and any(token.lower() in str(s).lower() for s in emp_skills):
                    score += 1
            if score or not skills:
                matches.append(
                    {
                        "id": emp.id, "name": emp.full_name or emp.id,
                        "title": getattr(emp, "title", None), "match_score": score,
                    }
                )
        matches.sort(key=lambda m: m["match_score"], reverse=True)
        return {
            "query_terms": skills,
            "candidates": matches[:10],
            "root_causes": [],
            "recommendations": [f"Consult {m['name']}" for m in matches[:3]] if matches else ["No expertise found"],
        }

    async def _health_evidence(self, db: AsyncSession, organization_id: str) -> dict[str, Any]:
        from app.autonomy.health_engine import health_engine

        health = await health_engine.latest(db, organization_id)
        dims = sorted(health.get("dimensions", {}).items(), key=lambda kv: kv[1])
        weakest = dims[:3] if dims else []
        return {
            "score": health.get("score"),
            "status": health.get("status"),
            "dimensions": health.get("dimensions", {}),
            "root_causes": [f"Lowest health: {name} ({value})" for name, value in weakest],
            "recommendations": [f"Invest in {name}" for name, _ in weakest],
        }

    async def _summary_evidence(
        self, db: AsyncSession, organization_id: str, question: str, now: Any
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
        docs = (
            await db.execute(
                select(func.count(Document.id)).where(Document.organization_id == organization_id)
            )
        ).scalar() or 0
        customers = (
            await db.execute(
                select(func.count(Customer.id)).where(Customer.organization_id == organization_id)
            )
        ).scalar() or 0
        meetings_30d = (
            await db.execute(
                select(func.count(Meeting.id)).where(
                    Meeting.organization_id == organization_id,
                    Meeting.start_at >= now - timedelta(days=30),
                )
            )
        ).scalar() or 0
        return {
            "organization": {
                "employees": employees, "projects": projects,
                "documents": docs, "customers": customers, "meetings_30d": meetings_30d,
            },
            "root_causes": [],
            "recommendations": [],
        }

    async def _learning_evidence(
        self, db: AsyncSession, organization_id: str, question: str
    ) -> dict[str, Any]:
        employees = (
            await db.execute(
                select(Employee).where(Employee.organization_id == organization_id).limit(300)
            )
        ).scalars().all()
        needs: list[dict[str, Any]] = []
        for emp in employees:
            skills = set(map(str, (getattr(emp, "skills", None) or []) + (getattr(emp, "skills_list", None) or [])))
            if len(skills) <= 1:
                needs.append({"name": emp.full_name or emp.id, "reason": "Minimal recorded skills"})
        return {
            "learning_needs": needs[:10],
            "root_causes": [f"{len(needs)} employee(s) have minimal skills"] if needs else [],
            "recommendations": ["Assign learning paths to low-skill employees"] if needs else ["Skills look healthy"],
        }

    async def _prediction_evidence(self, db: AsyncSession, organization_id: str) -> dict[str, Any]:
        from app.autonomy.prediction_engine import prediction_engine

        data = await prediction_engine.list(db, organization_id, status="open", limit=10)
        predictions = data["predictions"]
        return {
            "predictions": predictions,
            "root_causes": [p["title"] for p in predictions[:3]],
            "recommendations": [f"Mitigate: {p['title']}" for p in predictions[:3]],
        }

    async def _customer_evidence(self, db: AsyncSession, organization_id: str) -> dict[str, Any]:
        from app.models.customer import CustomerHealth

        low = (
            await db.execute(
                select(func.count(CustomerHealth.id))
                .join(Customer, Customer.id == CustomerHealth.customer_id)
                .where(Customer.organization_id == organization_id, CustomerHealth.score < 50)
            )
        ).scalar() or 0
        total = (
            await db.execute(
                select(func.count(Customer.id)).where(Customer.organization_id == organization_id)
            )
        ).scalar() or 0
        return {
            "customers": {"total": total, "below_50": low},
            "root_causes": [f"{low} customer(s) below 50 health"] if low else [],
            "recommendations": ["Run retention program"] if low else ["Customer health is stable"],
        }

    async def _risk_evidence(
        self, db: AsyncSession, organization_id: str, now: Any
    ) -> dict[str, Any]:
        from app.autonomy.strategy_engine import strategy_engine

        report = await strategy_engine.analyze(db, organization_id, period="ad-hoc")
        return {
            "risks": report["risks"],
            "findings": report["findings"],
            "root_causes": [r["detail"] for r in report["risks"]],
            "recommendations": [p["title"] for p in report["priorities"]],
        }

    def _conclude(self, intent: str, evidence: dict[str, Any]) -> str:
        root_causes = evidence.get("root_causes", [])
        if root_causes:
            return "; ".join(root_causes[:3])
        if intent == "who_knows" and evidence.get("candidates"):
            return f"Best matches: {', '.join(c['name'] for c in evidence['candidates'][:3])}"
        return "No significant issues detected"


reasoning_engine = ReasoningEngine()

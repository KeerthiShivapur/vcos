"""Enterprise reasoning engine — AI doesn't retrieve, AI reasons.

Given a question ("Why is Project Apollo delayed?"), the engine gathers
evidence across tasks, meetings, risks, people, dependencies, knowledge,
calendar, approvals, customers, budgets, learning and the organization graph,
then explains root causes with a connected explanation.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.models.customer import Customer
from app.models.employee import Employee
from app.models.knowledge import Decision, Document
from app.models.meeting import Meeting
from app.models.project import Project
from app.models.skill import ExpertiseScore, Skill
from app.models.task import Task, TaskDependency
from app.models.workflow import WorkflowApproval

INTENTS = (
    "why_delayed", "who_knows", "summarize", "recommend_next", "what_to_learn",
    "skill_gap", "explain_health", "predict_quarter", "strategic_risk",
    "customer_trends", "org_knowledge",
)

_INTENT_NOISE = frozenset(
    {
        "who", "knows", "know", "knowing", "expert", "experts", "help", "should",
        "what", "why", "is", "are", "the", "this", "on", "in", "about", "with",
        "how", "me", "my", "for", "best", "match", "someone", "to",
    }
)

_CLAIM_CONFIDENCE = {"matched": 0.85, "direct": 0.9, "recent": 0.65}

# Slice 4D.3 — question shapes that ask about organizational history.
_HISTORY_TRIGGERS = (
    "before", "again", "previously", "last time", "similar", "experience",
    "experienced", "history", "learned", "lesson", "remember", "happened",
    "prior", "past", "like this",
)


def _claim_text(item: dict[str, Any]) -> str:
    title = item["title"]
    detail = item.get("detail")
    etype = item["type"]
    if etype == "project":
        return f"{title} — {detail or 'active project'}"
    if etype == "task":
        return f"Task {title} is {detail or 'open'}"
    if etype == "decision":
        return f"Decision {title} is {detail or 'recorded'}"
    if etype == "conversation":
        return f"Conversation {title} ({detail or 'active'})"
    if etype == "message":
        return f"Message in {title} — {detail or 'recent'}"
    if etype == "scope":
        return f"Scope {title} is a {detail or 'governance'} scope"
    if etype == "approval_policy":
        return f"Approval policy {title}: {detail or 'active'}"
    if etype == "goal":
        return f"Goal {title}: {detail or 'tracked'}"
    if etype == "budget":
        return f"Budget {title}: {detail or 'tracked'}"
    if etype == "employee":
        return f"{title} ({detail or 'employee'}) is part of the organization"
    if etype == "document":
        return f"Document {title} — {detail or 'published knowledge'}"
    if etype == "wiki":
        return f"Wiki page {title} — {detail or 'published knowledge'}"
    if etype == "policy":
        return f"Policy {title} — {detail or 'published knowledge'}"
    if etype == "sop":
        return f"SOP {title} — {detail or 'published knowledge'}"
    if etype == "template":
        return f"Template {title} — {detail or 'published knowledge'}"
    return f"{title} is referenced by the question"


_CLAIM_TEMPLATES = {"project": _claim_text, "task": _claim_text, "decision": _claim_text,
                    "conversation": _claim_text, "message": _claim_text, "scope": _claim_text,
                    "approval_policy": _claim_text, "goal": _claim_text, "budget": _claim_text,
                    "employee": _claim_text, "document": _claim_text, "wiki": _claim_text,
                    "policy": _claim_text, "sop": _claim_text, "template": _claim_text}


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

    async def answer(
        self,
        db: AsyncSession,
        organization_id: str,
        question: str,
        *,
        user: Any,
        context: Optional[dict[str, Any]] = None,
        entity_type: Optional[str] = None,
        entity_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Slice 4D.1 — canonical, caller-aware answer with evidence claims.

        The context is always built governance-first: only evidence the
        caller may access is retrieved, so the same question answered by
        different callers differs exactly by their authorization.
        """
        from app.intelligence.company_context import build_context

        if context is None:
            context = await build_context(
                db, user, question,
                organization_id=organization_id,
                entity_type=entity_type,
                entity_id=entity_id,
            )
        claims = await self._claims_from_context(db, organization_id, question, context, user=user)
        return {
            "question": question,
            "claims": claims,
            "scope_ids": context.get("scope_ids", []),
            "answered_at": utcnow().isoformat(),
        }

    def _claim(self, item: dict[str, Any], scope_ids: list[str]) -> dict[str, Any]:
        confidence = _CLAIM_CONFIDENCE.get(item.get("relation", "matched"), 0.7)
        return {
            "claim": _CLAIM_TEMPLATES[item["type"]](item),
            "evidence": [
                {"type": item["type"], "id": item["id"], "title": item["title"], "url": item["url"]}
            ],
            "confidence": confidence,
            "auth_scope": {"scope_ids": scope_ids},
            "timestamp": item.get("timestamp", utcnow().isoformat()),
        }

    async def _claims_from_context(
        self,
        db: AsyncSession,
        organization_id: str,
        question: str,
        context: dict[str, Any],
        user: Optional[Any] = None,
    ) -> list[dict[str, Any]]:
        evidence = context.get("evidence", [])
        scope_ids = context.get("scope_ids", [])
        claims: list[dict[str, Any]] = []
        for item in evidence:
            claims.append(self._claim(item, scope_ids))

        lowered = question.lower()
        if "delayed" in lowered or "blocked" in lowered or "slowing" in lowered:
            claims.extend(await self._dependency_claims(db, organization_id, evidence, scope_ids))
        if "who knows" in lowered or "knows this" in lowered or "expert" in lowered:
            claims.extend(await self._expertise_claims(db, organization_id, question, context, scope_ids))
        claims.extend(await self._pattern_claims(db, organization_id, lowered, scope_ids, user=user))
        claims.extend(await self._insight_claims(db, organization_id, lowered, scope_ids, user=user))
        if user is not None:
            claims.extend(
                await self._historical_memory_claims(db, organization_id, lowered, scope_ids, user=user)
            )

        if not claims:
            claims = await self._overview_claims(db, organization_id, scope_ids)
        return claims

    async def _pattern_claims(
        self,
        db: AsyncSession,
        organization_id: str,
        lowered: str,
        scope_ids: list[str],
        user: Optional[Any] = None,
    ) -> list[dict[str, Any]]:
        """Slice 4D.4 — universal organizational pattern intelligence in answers.

        Pattern questions ("why do delays keep happening?", "is this a
        recurring problem?") surface evidence-backed patterns the caller may
        actually access — never observation buffers, never hidden patterns.
        """
        asks_patterns = any(
            trigger in lowered
            for trigger in (
                "pattern", "recurring", "repeating", "keeps", "always",
                "bottleneck", "repeatedly", "tendency", "systemic",
            )
        )
        if not asks_patterns:
            return []
        if user is None:
            return []
        from app.intelligence.pattern_engine import pattern_engine

        result = await pattern_engine.list_visible(
            db, organization_id=organization_id, user=user, limit=5
        )
        claims: list[dict[str, Any]] = []
        for pattern in result.get("patterns", []):
            confidence = round(float(pattern.get("confidence") or 0.4), 2)
            title = pattern.get("title") or pattern.get("pattern_type")
            claims.append({
                "claim": (
                    f"Recurring pattern ({pattern.get('family')}): {title} "
                    f"— seen {pattern.get('occurrence_count')}x over "
                    f"{pattern.get('time_window_days') or 'recent'} days, "
                    f"lifecycle {pattern.get('status')}."
                ),
                "evidence": [
                    {
                        "type": "pattern",
                        "id": pattern["id"],
                        "title": title,
                        "url": f"/brain/patterns/{pattern['id']}",
                    }
                ],
                "confidence": confidence,
                "auth_scope": {"scope_ids": scope_ids},
                "timestamp": pattern.get("last_seen") or utcnow().isoformat(),
                "kind": "pattern",
                "family": pattern.get("family"),
                "pattern_type": pattern.get("pattern_type"),
                "occurrence_count": pattern.get("occurrence_count"),
            })
        return claims

    async def _insight_claims(
        self,
        db: AsyncSession,
        organization_id: str,
        lowered: str,
        scope_ids: list[str],
        user: Optional[Any] = None,
    ) -> list[dict[str, Any]]:
        """Slice 4D.5 — universal company insights in answers.

        Insight questions ("what's happening in the company?", "why is my
        project stuck?", "is anything systemic?") surface the caller's
        visible insights — observation only, never recommendation, labeled
        with their compositional confidence so they can never be mistaken
        for prescriptive advice.
        """
        asks_insights = any(
            trigger in lowered
            for trigger in (
                "what's happening", "what is happening", "whats happening",
                "what is going on", "whats going on", "what's going on",
                "company insight", "insight", "systemic", "overall",
                "why is", "why are", "stuck", "happening",
            )
        )
        if not asks_insights:
            return []
        if user is None:
            return []
        from app.intelligence.insight_engine import insight_engine

        result = await insight_engine.list_visible(
            db, organization_id=organization_id, user=user, limit=5
        )
        claims: list[dict[str, Any]] = []
        for insight in result.get("insights", []):
            confidence = round(float(insight.get("confidence") or 0.4), 2)
            title = insight.get("title") or insight.get("insight_type")
            claims.append({
                "claim": (
                    f"Company insight ({insight.get('insight_type')}): {title} — "
                    f"severity {insight.get('severity')} "
                    f"(confidence {confidence})."
                ),
                "evidence": [
                    {
                        "type": "insight",
                        "id": insight["id"],
                        "title": title,
                        "url": f"/brain/insights/{insight['id']}",
                    }
                ],
                "confidence": confidence,
                "auth_scope": {"scope_ids": scope_ids},
                "timestamp": insight.get("last_observed_at") or utcnow().isoformat(),
                "kind": "insight",
                "insight_type": insight.get("insight_type"),
                "severity": insight.get("severity"),
            })
        return claims

    async def _historical_memory_claims(
        self,
        db: AsyncSession,
        organization_id: str,
        lowered: str,
        scope_ids: list[str],
        *,
        user: Any,
    ) -> list[dict[str, Any]]:
        """Slice 4D.3 — historical experiences/lessons in brain answers.

        History questions ("have we experienced something like this before?")
        retrieve evidence-backed memories the caller may actually access. The
        resulting claims are explicitly labeled as historical memory (with
        fact kind, outcome and confidence) so they can never be mistaken for
        current facts.
        """
        asks_history = any(trigger in lowered for trigger in _HISTORY_TRIGGERS)
        asks_delay = any(word in lowered for word in ("delayed", "blocked", "slowing"))
        if not (asks_history or asks_delay):
            return []
        from app.memory.memory_store import search as memory_search

        result = await memory_search(
            db,
            organization_id=organization_id,
            user=user,
            query=lowered,
            limit=3 if asks_history else 2,
        )
        claims: list[dict[str, Any]] = []
        now = utcnow()
        for memory in result.get("memories", []):
            category = memory.get("memory_category")
            kind = memory.get("fact_kind")
            title = memory.get("title") or "recorded experience"
            if category == "lesson":
                text = f"Lesson learned previously: {title}"
            elif category == "outcome":
                text = (
                    f"Previously recorded outcome ({memory.get('outcome_type')}): {title}"
                )
            else:
                text = f"Historical experience: {title}"
            claims.append({
                "claim": text,
                "evidence": [
                    {
                        "type": "memory",
                        "id": memory["id"],
                        "title": title,
                        "url": f"/brain/memory/{memory['id']}",
                    }
                ],
                "confidence": round(float(memory.get("confidence") or 0.6), 2),
                "auth_scope": {"scope_ids": scope_ids},
                "timestamp": memory.get("occurred_at") or now.isoformat(),
                "kind": kind,
                "memory_category": category,
                "outcome_type": memory.get("outcome_type"),
            })
        if not claims and asks_delay:
            claims.append({
                "claim": "No similar historical experience is recorded for this situation",
                "evidence": [],
                "confidence": 0.5,
                "auth_scope": {"scope_ids": scope_ids},
                "timestamp": now.isoformat(),
                "kind": "observation",
                "memory_category": "event",
            })
        return claims

    async def _dependency_claims(
        self,
        db: AsyncSession,
        organization_id: str,
        evidence: list[dict[str, Any]],
        scope_ids: list[str],
    ) -> list[dict[str, Any]]:
        """Slice 4D.1 — dependency input for delay questions (bounded, indexed)."""
        project_ids = [e["id"] for e in evidence if e["type"] == "project"]
        if not project_ids:
            return []
        project_ids = project_ids[:20]
        rows = (
            await db.execute(
                select(func.count(TaskDependency.id))
                .join(Task, Task.id == TaskDependency.task_id)
                .where(
                    Task.organization_id == organization_id,
                    Task.project_id.in_(project_ids),
                )
            )
        ).scalar() or 0
        if not rows:
            return []
        return [{
            "claim": f"{rows} task dependencies exist across {len(project_ids)} project(s)",
            "evidence": [
                {"type": "project", "id": pid, "title": pid, "url": f"/projects/{pid}"}
                for pid in project_ids[:3]
            ],
            "confidence": 0.7,
            "auth_scope": {"scope_ids": scope_ids},
            "timestamp": utcnow().isoformat(),
        }]

    async def _expertise_claims(
        self,
        db: AsyncSession,
        organization_id: str,
        question: str,
        context: dict[str, Any],
        scope_ids: list[str],
    ) -> list[dict[str, Any]]:
        terms = [
            t for t in question.lower().split()
            if t not in _INTENT_NOISE and len(t) > 2
        ]
        if not terms:
            return []
        skills = (
            await db.execute(
                select(Skill)
                .where(Skill.organization_id == organization_id)
                .order_by(Skill.updated_at.desc())
                .limit(50)
            )
        ).scalars().all()
        matched_skill_ids = [
            s.id for s in skills
            if any(t in s.name.lower() for t in terms)
        ]
        if not matched_skill_ids:
            return []
        rows = (
            await db.execute(
                select(ExpertiseScore, Employee)
                .join(Employee, Employee.id == ExpertiseScore.employee_id)
                .where(
                    ExpertiseScore.organization_id == organization_id,
                    ExpertiseScore.skill_id.in_(matched_skill_ids),
                )
                .order_by(ExpertiseScore.score.desc())
                .limit(10)
            )
        ).all()
        claims: list[dict[str, Any]] = []
        for score, emp in rows:
            name = emp.display_name or f"{emp.first_name} {emp.last_name or ''}".strip()
            claims.append({
                "claim": f"{name} is the strongest match for {terms[0]} (expertise {score.score:.0f})",
                "evidence": [
                    {"type": "employee", "id": emp.id, "title": name, "url": f"/people/{emp.id}"}
                ],
                "confidence": min(0.95, 0.5 + score.score / 100),
                "auth_scope": {"scope_ids": scope_ids},
                "timestamp": utcnow().isoformat(),
            })
        return claims

    async def _overview_claims(
        self, db: AsyncSession, organization_id: str, scope_ids: list[str]
    ) -> list[dict[str, Any]]:
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
        decisions = (
            await db.execute(
                select(func.count(Decision.id)).where(Decision.organization_id == organization_id)
            )
        ).scalar() or 0
        now = utcnow()
        claim = {
            "claim": f"The company has {employees} employee(s) and {projects} project(s)",
            "evidence": [],
            "confidence": 0.6,
            "auth_scope": {"scope_ids": scope_ids},
            "timestamp": now.isoformat(),
        }
        claims = [claim]
        if decisions:
            claims.append({
                "claim": f"{decisions} decision(s) are recorded in the decision log",
                "evidence": [],
                "confidence": 0.6,
                "auth_scope": {"scope_ids": scope_ids},
                "timestamp": now.isoformat(),
            })
        return claims

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
        """Bounded, indexed expertise lookup: skills -> expertise scores -> people.

        Replaces the legacy full-employee scan that read nonexistent
        ``full_name``/``skills`` attributes on the Employee model.
        """
        terms = [
            t for t in question.replace("who", "").replace("knows", "").replace("?", "").split()
            if t not in _INTENT_NOISE and len(t) > 2
        ]
        skills = (
            await db.execute(
                select(Skill)
                .where(Skill.organization_id == organization_id)
                .order_by(Skill.updated_at.desc())
                .limit(50)
            )
        ).scalars().all()
        matched_skill_ids = [
            s.id for s in skills
            if any(t in s.name.lower() for t in terms)
        ]
        if not matched_skill_ids:
            return {"query_terms": terms, "candidates": [], "root_causes": [],
                    "recommendations": ["No expertise found"]}
        rows = (
            await db.execute(
                select(ExpertiseScore, Employee)
                .join(Employee, Employee.id == ExpertiseScore.employee_id)
                .where(
                    ExpertiseScore.organization_id == organization_id,
                    ExpertiseScore.skill_id.in_(matched_skill_ids),
                )
                .order_by(ExpertiseScore.score.desc())
                .limit(10)
            )
        ).all()
        matches: list[dict[str, Any]] = []
        for score, emp in rows:
            name = emp.display_name or f"{emp.first_name} {emp.last_name or ''}".strip()
            matches.append({
                "id": emp.id, "name": name,
                "title": emp.designation, "match_score": round(score.score, 2),
            })
        return {
            "query_terms": terms,
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

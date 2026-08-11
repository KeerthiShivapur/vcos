"""Phase 20 — Universal reasoning engine (enterprise reasoning).

Instead of retrieving information, the brain reasons: it analyzes projects,
meetings, dependencies, knowledge, approvals, hiring, training, community,
customers, budget and historical trends, then produces a connected
explanation with evidence and recommendations.
"""

from __future__ import annotations

from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.autonomy.awareness_engine import awareness_engine
from app.intelligence_network.reasoning_engine import reasoning_engine as network_reasoning
from app.intelligence_network.strategic_ai import strategic_ai


class ReasoningEngine:
    """Universal reasoning: questions, advice and topic explanations."""

    async def ask(
        self, db: AsyncSession, organization_id: str, question: str
    ) -> dict[str, Any]:
        """Answer any enterprise question with cross-module evidence."""
        return await network_reasoning.ask(db, organization_id, question)

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
        """Slice 4D.1 — canonical caller-aware answer (governance-scoped claims)."""
        return await network_reasoning.answer(
            db, organization_id, question,
            user=user, context=context, entity_type=entity_type, entity_id=entity_id,
        )

    async def advise(
        self, db: AsyncSession, organization_id: str, question: str
    ) -> dict[str, Any]:
        """Strategic advice with options, confidence and a recommendation."""
        return await strategic_ai.advise(db, organization_id, question)

    async def explain(
        self, db: AsyncSession, organization_id: str, topic: str
    ) -> dict[str, Any]:
        """Explain one domain of the company from the current state."""
        state = await awareness_engine.latest(db, organization_id)
        current = state.get("state") or {}
        known = {
            "projects": current.get("projects", {}),
            "tasks": current.get("tasks", {}),
            "employees": current.get("employees", {}),
            "customers": current.get("customers", {}),
            "knowledge": current.get("knowledge", {}),
            "learning": current.get("learning", {}),
            "budget": current.get("budget", {}),
            "hiring": current.get("hiring", {}),
            "meetings": current.get("meetings", {}),
            "goals": current.get("goals", {}),
        }
        key = topic.strip().lower()
        if key not in known and key not in ("company", "health", "overview"):
            key = "overview"
        if key in ("company", "health", "overview"):
            sections = {k: v for k, v in known.items() if v}
            conclusion = (
                f"The company currently runs {current.get('projects', {}).get('active', 0)} "
                f"active projects with {current.get('employees', {}).get('total', 0)} employees."
            )
            return {"topic": topic, "sections": sections, "conclusion": conclusion,
                    "score": state.get("score"), "snapshot_at": state.get("snapshot_at")}
        section = known[key]
        return {
            "topic": topic,
            "domain": key,
            "evidence": section,
            "conclusion": self._conclude(key, section),
            "score": state.get("score"),
        }

    def _conclude(self, key: str, section: dict[str, Any]) -> str:
        if key == "projects":
            return f"{section.get('active', 0)} active of {section.get('total', 0)} projects."
        if key == "tasks":
            return f"{section.get('overdue', 0)} overdue tasks right now."
        if key == "employees":
            return f"{section.get('total', 0)} employees, {section.get('online', 0)} online now."
        if key == "customers":
            return f"{section.get('total', 0)} customers tracked."
        if key == "knowledge":
            return (f"{section.get('documents', 0)} documents, {section.get('wiki_pages', 0)} wiki pages, "
                    f"{section.get('added_7d', 0)} added in the last 7 days.")
        if key == "learning":
            return f"{section.get('completed_enrollments', 0)} completed enrollments across {section.get('courses', 0)} courses."
        if key == "budget":
            return f"Budget usage at {section.get('usage_percent', 0)}%."
        if key == "hiring":
            return f"{section.get('hired_30d', 0)} employee(s) hired in the last 30 days."
        if key == "meetings":
            return f"{section.get('total', 0)} meetings, {section.get('this_week', 0)} this week."
        if key == "goals":
            return f"{section.get('total', 0)} goals tracked."
        return f"{key.replace('_', ' ').title()}: {section}"


reasoning_engine = ReasoningEngine()

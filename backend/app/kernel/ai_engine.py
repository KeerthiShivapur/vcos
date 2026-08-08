"""Phase 20 — AI engine (the universal AI gateway).

One AI for the whole company. Instead of separate project/meeting/knowledge
AIs, every question is answered with the same reasoning, memory, context and
company understanding wired through the kernel.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.autonomy.executive_briefing import executive_briefing_engine
from app.autonomy.awareness_engine import awareness_engine
from app.intelligence_network.reasoning_engine import reasoning_engine as network_reasoning
from app.intelligence_network.strategic_ai import strategic_ai


class AIEngine:
    """Universal AI front door for employees, managers and executives."""

    async def answer(
        self, db: AsyncSession, organization_id: str, question: str
    ) -> dict[str, Any]:
        """Answer any company question with cross-module evidence."""
        return await network_reasoning.ask(db, organization_id, question)

    async def advise(
        self, db: AsyncSession, organization_id: str, question: str
    ) -> dict[str, Any]:
        """Strategic advice with evidence, options and a recommendation."""
        return await strategic_ai.advise(db, organization_id, question)

    async def brief(self, db: AsyncSession, organization_id: str) -> dict[str, Any]:
        """Generate (or return) the executive morning briefing."""
        return await executive_briefing_engine.generate(db, organization_id)

    async def latest_brief(self, db: AsyncSession, organization_id: str) -> dict[str, Any]:
        """Return the most recent briefing (generates one on first use)."""
        return await executive_briefing_engine.latest(db, organization_id)

    async def explain_company(self, db: AsyncSession, organization_id: str) -> dict[str, Any]:
        """Explain the current organizational state in plain language."""
        state = await awareness_engine.latest(db, organization_id)
        current = state.get("state") or {}
        projects = current.get("projects", {})
        tasks = current.get("tasks", {})
        employees = current.get("employees", {})
        budget = current.get("budget", {})
        lines = [
            f"{employees.get('total', 0)} employees ({employees.get('online', 0)} online), "
            f"{projects.get('active', 0)} active of {projects.get('total', 0)} projects, "
            f"{tasks.get('open', 0)} open tasks with {tasks.get('overdue', 0)} overdue.",
            f"Budget usage is {budget.get('usage_percent', 0)}%.",
        ]
        if tasks.get("overdue", 0):
            lines.append("Overdue tasks are the current delivery risk.")
        else:
            lines.append("No overdue tasks right now.")
        return {
            "company_summary": " ".join(lines),
            "state": current,
            "score": state.get("score"),
            "snapshot_at": state.get("snapshot_at"),
        }


ai_engine = AIEngine()

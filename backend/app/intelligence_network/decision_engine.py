"""Decision intelligence engine — decisions with full organizational context.

Connects the decision-support service to the organization graph and memory so
every important decision is stored with context, alternatives, participants,
outcome, results and lessons.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.autonomy.decision_support import decision_support_service
from app.intelligence_network.organization_graph import organization_graph


class DecisionEngine:
    async def create_with_context(
        self,
        db: AsyncSession,
        organization_id: str,
        *,
        title: str,
        question: str | None = None,
        category: str = "strategy",
        context: str | None = None,
        alternatives: list[dict[str, Any]] | None = None,
        created_by: str | None = None,
        commit: bool = False,
    ) -> dict[str, Any]:
        """Create a decision case enriched with live organizational context."""
        case = await decision_support_service.create_case(
            db,
            organization_id,
            title=title,
            question=question,
            category=category,
            context=context,
            alternatives=alternatives,
            created_by=created_by,
        )
        try:
            graph = await organization_graph.stats(db, organization_id)
            case["analysis"]["organization_graph"] = {
                "nodes": graph["total_nodes"], "edges": graph["total_edges"],
            }
        except Exception:  # pragma: no cover - defensive
            pass
        if commit:
            await db.commit()
        return case

    async def list(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return await decision_support_service.list(*args, **kwargs)

    async def get(self, *args: Any, **kwargs: Any) -> dict[str, Any] | None:
        return await decision_support_service.get(*args, **kwargs)

    async def decide(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return await decision_support_service.decide(*args, **kwargs)


decision_engine = DecisionEngine()

"""Phase 20 — Organization kernel (the universal company brain).

The kernel is the single integration point: it wires the graph, memory,
AI, reasoning, search, context, health, events, analytics and orchestration
engines together so the whole platform behaves as one living company.
"""

from __future__ import annotations

from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.autonomy.awareness_engine import awareness_engine
from app.kernel.ai_engine import AIEngine, ai_engine
from app.kernel.analytics_engine import AnalyticsEngine, analytics_engine
from app.kernel.context_engine import ContextEngine, context_engine
from app.kernel.event_engine import EventEngine, event_engine
from app.kernel.governance_engine import GovernanceEngine, governance_engine
from app.kernel.graph_engine import GraphEngine, graph_engine
from app.kernel.health_engine import HealthEngine, health_engine
from app.kernel.intelligence_engine import IntelligenceEngine, intelligence_engine
from app.kernel.memory_engine import MemoryEngine, memory_engine
from app.kernel.orchestration_engine import OrchestrationEngine, orchestration_engine
from app.kernel.reasoning_engine import ReasoningEngine, reasoning_engine
from app.kernel.resilience_engine import ResilienceEngine, resilience_engine
from app.kernel.search_engine import SearchEngine, search_engine

CAPABILITIES: list[dict[str, Any]] = [
    {"id": "identity", "name": "Identity & Permissions", "description": "One auth, one RBAC, one multi-tenant boundary."},
    {"id": "graph", "name": "Living Organization Graph", "description": "Every entity is a node in one searchable network."},
    {"id": "memory", "name": "Company Memory", "description": "Decisions, lessons, milestones and history never forgotten."},
    {"id": "knowledge", "name": "Knowledge System", "description": "Documents, wiki, policies, SOPs and quality intelligence."},
    {"id": "ai", "name": "Universal AI", "description": "One reasoning engine with one company understanding."},
    {"id": "context", "name": "Universal Context", "description": "Context flows between every module automatically."},
    {"id": "health", "name": "Company Health", "description": "One unified health score across every domain."},
    {"id": "events", "name": "Event Bus", "description": "Every subsystem publishes to the same event stream."},
    {"id": "search", "name": "Universal Search", "description": "One search across the entire organization."},
    {"id": "timeline", "name": "Company Timeline", "description": "Travel through company history end to end."},
    {"id": "analytics", "name": "Analytics", "description": "One analytics surface over the whole company."},
    {"id": "orchestration", "name": "Continuous Evolution", "description": "The company observes, learns and improves automatically."},
    {"id": "governance", "name": "Responsible AI Governance", "description": "Explainable recommendations, human review and approval gates."},
    {"id": "resilience", "name": "Enterprise Resilience", "description": "Disruption scenarios and coordinated response plans."},
]


class OrganizationKernel:
    """The hub every module plugs into."""

    def __init__(
        self,
        ai: AIEngine = ai_engine,
        analytics: AnalyticsEngine = analytics_engine,
        context: ContextEngine = context_engine,
        events: EventEngine = event_engine,
        governance: GovernanceEngine = governance_engine,
        graph: GraphEngine = graph_engine,
        health: HealthEngine = health_engine,
        intelligence: IntelligenceEngine = intelligence_engine,
        memory: MemoryEngine = memory_engine,
        orchestration: OrchestrationEngine = orchestration_engine,
        reasoning: ReasoningEngine = reasoning_engine,
        resilience: ResilienceEngine = resilience_engine,
        search: SearchEngine = search_engine,
    ) -> None:
        self.ai = ai
        self.analytics = analytics
        self.context = context
        self.events = events
        self.governance = governance
        self.graph = graph
        self.health = health
        self.intelligence = intelligence
        self.memory = memory
        self.orchestration = orchestration
        self.reasoning = reasoning
        self.resilience = resilience
        self.search = search

    def capabilities(self) -> dict[str, Any]:
        return {"phase": 20, "name": "Universal Organizational Intelligence Network",
                "capabilities": CAPABILITIES}

    async def state(self, db: AsyncSession, organization_id: str) -> dict[str, Any]:
        return await awareness_engine.latest(db, organization_id)

    async def overview(self, db: AsyncSession, organization_id: str) -> dict[str, Any]:
        """The one living company view: everything connected."""
        state = await self.state(db, organization_id)
        health = await self.health.latest(db, organization_id)
        graph = await self.graph.stats(db, organization_id)
        intelligence = await self.intelligence.latest(db, organization_id)
        memories = await self.memory.list_memories(db, organization_id, limit=5)
        timeline = await self.memory.list_timeline(db, organization_id, limit=10)
        events = await self.events.list(db, organization_id, limit=10)
        analytics = await self.analytics.overview(db, organization_id)
        return {
            "organization_id": organization_id,
            "state": state,
            "health": health,
            "graph": graph,
            "intelligence": intelligence,
            "memory": {"total": memories["total"], "latest": memories["memories"]},
            "timeline": {"total": timeline["total"], "latest": timeline["entries"]},
            "events": events,
            "analytics": analytics,
            "capabilities": self.capabilities(),
        }

    async def evolve(self, db: AsyncSession, organization_id: str) -> dict[str, Any]:
        return await self.orchestration.run_cycle(db, organization_id)

    async def ask(self, db: AsyncSession, organization_id: str, question: str) -> dict[str, Any]:
        return await self.ai.answer(db, organization_id, question)

    async def advise(self, db: AsyncSession, organization_id: str, question: str) -> dict[str, Any]:
        return await self.ai.advise(db, organization_id, question)


organization_kernel = OrganizationKernel()

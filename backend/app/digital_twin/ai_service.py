"""Twin AI Service (Phase 18.13) — "Ask the company anything".

Natural-language querying over the organizational digital twin. The engine
runs fully deterministically when AI_PROVIDER=none: queries are routed to a
semantic intent handler that answers from live twin, health, prediction,
forecast, recommendation, simulation and decision data.
"""

import logging
import re
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.digital_twin.decision_service import decision_service
from app.digital_twin.executive_service import executive_service
from app.digital_twin.forecasting_service import forecasting_service
from app.digital_twin.health_service import health_service
from app.digital_twin.optimization_service import optimization_service
from app.digital_twin.prediction_service import prediction_service
from app.digital_twin.recommendation_service import recommendation_service
from app.digital_twin.simulation_service import simulation_service
from app.digital_twin.twin_service import digital_twin_service

logger = logging.getLogger("vcos.digital_twin.ai")

INTENT_KEYWORDS = {
    "health": ["health", "healthy", "wellbeing", "wellness", "score"],
    "risk": ["risk", "threat", "danger", "worry", "concern"],
    "people": ["people", "employee", "staff", "headcount", "hire", "talent", "team"],
    "project": ["project", "task", "deliverable", "backlog", "milestone"],
    "finance": ["finance", "revenue", "cost", "budget", "money", "cash", "fund"],
    "knowledge": ["knowledge", "document", "learn", "skill", "course"],
    "recommendation": ["recommend", "advice", "should", "improve", "focus"],
    "forecast": ["forecast", "predict", "future", "trend", "growth", "projection"],
    "simulation": ["simulate", "scenario", "what if", "what-if"],
    "optimization": ["optimize", "efficiency", "waste", "automate", "restructure"],
    "decision": ["decision", "outcome", "lesson", "learned"],
    "overview": ["overview", "summary", "status", "brief", "general", "everything", "company"],
}


class TwinAIService:
    """Answers natural-language questions about the company."""

    async def ask(self, db: AsyncSession, organization_id: str, question: str) -> dict[str, Any]:
        intent = self._route(question)
        handler = getattr(self, f"_answer_{intent}", self._answer_overview)
        answer, context = await handler(db, organization_id, question)
        return {
            "question": question,
            "intent": intent,
            "answer": answer,
            "context": context,
            "confidence": 0.85 if intent in INTENT_KEYWORDS else 0.6,
        }

    def _route(self, question: str) -> str:
        text = question.lower()
        best, best_hits = "overview", 0
        for intent, keywords in INTENT_KEYWORDS.items():
            hits = sum(1 for k in keywords if k in text)
            if hits > best_hits:
                best, best_hits = intent, hits
        return best

    async def _answer_overview(self, db, organization_id, question) -> tuple[str, dict]:
        dash = await executive_service.dashboard(db, organization_id)
        twin = dash["twin"] or {}
        counts = twin.get("entity_counts", {})
        health = dash["health"] or {}
        return (
            f"The company model shows {counts.get('active_employees', 0)} active employees, "
            f"{counts.get('active_projects', 0)} active projects and {counts.get('open_tasks', 0)} open tasks. "
            f"Health is {health.get('status', 'unknown')} at {health.get('score', 0)}/100.",
            {"twin": twin, "health": health},
        )

    async def _answer_health(self, db, organization_id, question) -> tuple[str, dict]:
        health = await health_service.latest(db, organization_id) or {}
        score = health.get("score", 0)
        breakdown = health.get("breakdown") or {}
        dims = ", ".join(f"{k}={v.get('score', 0)}" for k, v in breakdown.items()) if breakdown else "not computed yet"
        return (
            f"Organization health is {health.get('status', 'unknown')} at {score}/100. Dimensions: {dims}.",
            health,
        )

    async def _answer_risk(self, db, organization_id, question) -> tuple[str, dict]:
        predictions = await prediction_service.list(db, organization_id, status="active")
        risky = [p for p in predictions if p["level"] in ("high", "critical")]
        if risky:
            text = "Highest risks: " + "; ".join(f"{p['title']} ({p['probability']}% {p['level']})" for p in risky[:5])
        else:
            text = "No high or critical risks are currently predicted."
        return text, {"risks": risky, "count": len(predictions)}

    async def _answer_people(self, db, organization_id, question) -> tuple[str, dict]:
        dash = await executive_service.dashboard(db, organization_id)
        counts = (dash["twin"] or {}).get("entity_counts", {})
        return (
            f"There are {counts.get('employees', 0)} employees in the model "
            f"({counts.get('active_employees', 0)} active) across {counts.get('departments', 0)} departments.",
            counts,
        )

    async def _answer_project(self, db, organization_id, question) -> tuple[str, dict]:
        dash = await executive_service.dashboard(db, organization_id)
        counts = (dash["twin"] or {}).get("entity_counts", {})
        return (
            f"{counts.get('active_projects', 0)} of {counts.get('projects', 0)} projects are active with "
            f"{counts.get('open_tasks', 0)} open tasks (completion {counts.get('completion_pct', 0)}%).",
            counts,
        )

    async def _answer_finance(self, db, organization_id, question) -> tuple[str, dict]:
        dash = await executive_service.dashboard(db, organization_id)
        counts = (dash["twin"] or {}).get("entity_counts", {})
        return (
            f"Budget utilization is {counts.get('budget_utilization', 0)}% with revenue {counts.get('revenue', 0)}, "
            f"costs {counts.get('costs', 0)} and profitability {counts.get('profitability_pct', 0)}%.",
            counts,
        )

    async def _answer_knowledge(self, db, organization_id, question) -> tuple[str, dict]:
        dash = await executive_service.dashboard(db, organization_id)
        counts = (dash["twin"] or {}).get("entity_counts", {})
        return (
            f"The knowledge base holds {counts.get('knowledge_indexed', 0)} indexed items from "
            f"{counts.get('knowledge_sources', 0)} sources with {counts.get('courses', 0)} learning assets.",
            counts,
        )

    async def _answer_recommendation(self, db, organization_id, question) -> tuple[str, dict]:
        recs = await recommendation_service.list(db, organization_id, status="active")
        if not recs:
            return "No active recommendations. I can generate some from current data.", {"count": 0}
        return (
            "Active recommendations: " + "; ".join(f"{r['title']} ({r['priority']})" for r in recs[:5]) + ".",
            {"recommendations": recs, "count": len(recs)},
        )

    async def _answer_forecast(self, db, organization_id, question) -> tuple[str, dict]:
        forecasts = await forecasting_service.list(db, organization_id, limit=20)
        if not forecasts:
            return "No forecasts yet. Generate them from the intelligence center.", {"count": 0}
        lines = []
        for f in forecasts[:5]:
            latest = f["series"][-1] if f["series"] else {"value": 0}
            lines.append(f"{f['dimension']}: ~{latest.get('value', 0)} ({f['trend']})")
        return "Forecasts: " + "; ".join(lines) + ".", {"forecasts": forecasts, "count": len(forecasts)}

    async def _answer_simulation(self, db, organization_id, question) -> tuple[str, dict]:
        simulations = await simulation_service.list(db, organization_id, limit=5)
        if not simulations:
            return "No simulations run yet. Run one from the intelligence center.", {"count": 0}
        latest = simulations[0]
        return (
            f"Most recent simulation: {latest['title']} — feasibility {latest['results'].get('feasibility', 0)}%, "
            f"risk {latest['results'].get('risk', 0)}/100.",
            {"simulations": simulations, "count": len(simulations)},
        )

    async def _answer_optimization(self, db, organization_id, question) -> tuple[str, dict]:
        suggestions = await optimization_service.list(db, organization_id, status="suggested", limit=5)
        if not suggestions:
            return "No optimization suggestions pending.", {"count": 0}
        return (
            "Suggestions: " + "; ".join(f"{s['title']} (impact {s['impact']})" for s in suggestions[:5]) + ".",
            {"suggestions": suggestions, "count": len(suggestions)},
        )

    async def _answer_decision(self, db, organization_id, question) -> tuple[str, dict]:
        decisions = await decision_service.list(db, organization_id, limit=10)
        if not decisions:
            return "No decisions recorded yet.", {"count": 0}
        return (
            "Recent decisions: " + "; ".join(f"{d['decision'][:60]}" for d in decisions[:5]) + ".",
            {"decisions": decisions, "count": len(decisions)},
        )


twin_ai_service = TwinAIService()
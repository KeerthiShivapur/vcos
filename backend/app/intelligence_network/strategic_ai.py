"""Executive strategic advisor — strategic reasoning across the organization.

CEO questions ("Should we expand? Acquire? Delay the release? Increase hiring?
Reduce meetings? Invest in AI?") are answered with organizational evidence via
the reasoning engine, strategy engine and simulation engine.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.autonomy.simulation_engine import simulation_engine
from app.autonomy.strategy_engine import strategy_engine
from app.intelligence_network.reasoning_engine import reasoning_engine


class StrategicAI:
    async def advise(self, db: AsyncSession, organization_id: str, question: str) -> dict[str, Any]:
        lowered = question.lower()
        topic = self._classify(lowered)
        options: list[dict[str, Any]] = []
        evidence: dict[str, Any] = {}

        if topic == "expansion":
            evidence = await self._expansion_evidence(db, organization_id)
            options = [
                {
                    "title": "Expand gradually",
                    "detail": "Small footprint first; validate demand before scaling.",
                    "pros": ["Lower risk", "Faster break-even"],
                    "cons": ["Slower market capture"],
                },
                {
                    "title": "Full-scale expansion",
                    "detail": "Commit infrastructure, hiring and support upfront.",
                    "pros": ["Market leadership", "Efficiency at scale"],
                    "cons": ["High capital risk"],
                },
            ]
        elif topic == "acquisition":
            evidence = await self._acquisition_evidence(db, organization_id)
            options = [
                {
                    "title": "Acquire for capability",
                    "detail": "Buy a team or product to close a strategic gap.",
                    "pros": ["Fast capability", "Access to talent"],
                    "cons": ["Integration cost", "Culture risk"],
                },
                {
                    "title": "Build internally",
                    "detail": "Develop the capability in-house.",
                    "pros": ["Full control", "Cultural fit"],
                    "cons": ["Slower", "Costlier over time"],
                },
            ]
        elif topic == "hiring":
            evidence = await self._hiring_evidence(db, organization_id)
            options = [
                {
                    "title": "Increase hiring",
                    "detail": "Relieve overload and grow capacity.",
                    "pros": ["More throughput", "Less burnout"],
                    "cons": ["Budget pressure", "Onboarding lag"],
                },
                {
                    "title": "Optimize first",
                    "detail": "Automate and rebalance before hiring.",
                    "pros": ["Cheaper", "Faster payback"],
                    "cons": ["Capacity ceiling"],
                },
            ]
        elif topic == "meetings":
            evidence = await self._meeting_evidence(db, organization_id)
            options = [
                {
                    "title": "Reduce meetings",
                    "detail": "Move to async updates and shorter sessions.",
                    "pros": ["More focus time"],
                    "cons": ["Less alignment"],
                },
            ]
        elif topic == "ai_investment":
            evidence = await self._ai_evidence(db, organization_id)
            options = [
                {
                    "title": "Invest in AI",
                    "detail": "Automate repetitive work and gain intelligence.",
                    "pros": ["Productivity gain", "Better decisions"],
                    "cons": ["Adoption effort"],
                },
            ]
        elif topic == "release":
            evidence = await self._release_evidence(db, organization_id)
            options = [
                {
                    "title": "Delay the release",
                    "detail": "Protect quality when signals are negative.",
                    "pros": ["Quality", "Customer trust"],
                    "cons": ["Market timing"],
                },
            ]
        else:
            strategy = await strategy_engine.analyze(db, organization_id, period="ad-hoc")
            evidence = {
                "risks": strategy["risks"],
                "priorities": strategy["priorities"],
                "focus_areas": strategy["focus_areas"],
            }
            options = [{"title": p["title"], "detail": "From current strategy report"} for p in strategy["priorities"]]

        advice = self._recommend(topic, evidence)
        return {
            "question": question,
            "topic": topic,
            "evidence": evidence,
            "options": options,
            "recommendation": advice,
            "human_approval_required": True,
        }

    def _classify(self, lowered: str) -> str:
        if any(w in lowered for w in ("expand", "germany", "new office", "new market")):
            return "expansion"
        if any(w in lowered for w in ("acquire", "acquisition", "merge")):
            return "acquisition"
        if any(w in lowered for w in ("hire", "hiring", "engineer")):
            return "hiring"
        if any(w in lowered for w in ("meeting", "calendar")):
            return "meetings"
        if any(w in lowered for w in ("ai", "automation", "invest in")):
            return "ai_investment"
        if any(w in lowered for w in ("release", "launch", "delay")):
            return "release"
        return "general"

    async def _expansion_evidence(self, db: AsyncSession, organization_id: str) -> dict[str, Any]:
        from sqlalchemy import func

        from app.models.customer import Customer
        from app.models.employee import Employee

        employees = (
            await db.execute(
                select(func.count(Employee.id)).where(Employee.organization_id == organization_id)
            )
        ).scalar() or 0
        customers = (
            await db.execute(
                select(func.count(Customer.id)).where(Customer.organization_id == organization_id)
            )
        ).scalar() or 0
        return {
            "headcount": employees,
            "customers": customers,
            "readiness": "medium" if employees >= 20 and customers >= 10 else "low",
        }

    async def _acquisition_evidence(self, db: AsyncSession, organization_id: str) -> dict[str, Any]:
        from sqlalchemy import func

        from app.models.finance import Budget

        budgets = (
            await db.execute(
                select(Budget).where(Budget.organization_id == organization_id, Budget.status == "active")
            )
        ).scalars().all()
        allocated = sum(b.allocated_amount or 0 for b in budgets)
        return {"budget_allocated": allocated, "note": "Acquisition needs board approval and legal review"}

    async def _hiring_evidence(self, db: AsyncSession, organization_id: str) -> dict[str, Any]:
        from sqlalchemy import func

        from app.models.employee import Employee
        from app.models.task import Task

        employees = (
            await db.execute(
                select(func.count(Employee.id)).where(Employee.organization_id == organization_id)
            )
        ).scalar() or 0
        open_tasks = (
            await db.execute(
                select(func.count(Task.id)).where(
                    Task.organization_id == organization_id,
                    Task.status.notin_(["done", "completed", "cancelled"]),
                )
            )
        ).scalar() or 0
        return {
            "employees": employees,
            "open_tasks": open_tasks,
            "load_per_employee": round(open_tasks / max(employees, 1), 1),
        }

    async def _meeting_evidence(self, db: AsyncSession, organization_id: str) -> dict[str, Any]:
        from datetime import timedelta

        from sqlalchemy import func

        from app.core.timeutils import utcnow
        from app.models.meeting import Meeting

        meetings = (
            await db.execute(
                select(func.count(Meeting.id)).where(
                    Meeting.organization_id == organization_id,
                    Meeting.start_at >= utcnow() - timedelta(days=7),
                )
            )
        ).scalar() or 0
        return {"meetings_this_week": meetings}

    async def _ai_evidence(self, db: AsyncSession, organization_id: str) -> dict[str, Any]:
        from sqlalchemy import func

        from app.models.workflow import WorkflowExecution

        executions = (
            await db.execute(
                select(func.count(WorkflowExecution.id)).where(
                    WorkflowExecution.organization_id == organization_id
                )
            )
        ).scalar() or 0
        return {
            "automation_base": executions,
            "note": "Automation is already active; further AI investment compounds gains.",
        }

    async def _release_evidence(self, db: AsyncSession, organization_id: str) -> dict[str, Any]:
        from app.autonomy.prediction_engine import prediction_engine

        data = await prediction_engine.list(db, organization_id, status="open", limit=10)
        return {"open_predictions": data["predictions"]}

    def _recommend(self, topic: str, evidence: dict[str, Any]) -> str:
        if topic == "expansion":
            readiness = evidence.get("readiness", "low")
            return "Proceed with a phased expansion" if readiness == "medium" else "Strengthen the home market before expanding"
        if topic == "acquisition":
            return "Acquire only if a clear strategic gap exists; commission legal and financial due diligence"
        if topic == "hiring":
            load = evidence.get("load_per_employee", 0)
            return "Increase hiring now" if load and load > 6 else "Optimize existing capacity before hiring"
        if topic == "meetings":
            return "Reduce meeting load with async-first practices"
        if topic == "ai_investment":
            return "Invest in AI: automation base is active and ready to compound"
        if topic == "release":
            return "Delay the release if quality signals are negative"
        priorities = evidence.get("priorities", [])
        return priorities[0]["title"] if priorities else "Maintain current trajectory"


strategic_ai = StrategicAI()

"""Performance service (Phase 11.6 — Continuous Performance Management).

Cycles (draft → open → reviewing → closed), goals with progress tracking and
reviews (self / manager / peer / 360). Completed reviews feed AI summaries,
the organization graph and analytics; promotion readiness is a separate
career concern (Phase 10.6 PromotionSignal).
"""

import logging
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.events.event_bus import EventBus
from app.hr.parse import to_date
from app.models.employee import Employee
from app.models.hr import PerformanceCycle, PerformanceGoal, PerformanceReview

logger = logging.getLogger("vcos.hr.performance")

_event_bus = EventBus()

CYCLE_STATUSES = ["draft", "open", "reviewing", "closed"]
REVIEW_KINDS = ["self", "manager", "peer", "360"]


class PerformanceService:
    # ------------------------------------------------------------------ cycles

    async def create_cycle(self, db: AsyncSession, *, organization_id: str, data: dict[str, Any], created_by: Optional[str] = None) -> PerformanceCycle:
        cycle = PerformanceCycle(
            organization_id=organization_id,
            name=data["name"],
            period=data.get("period") or {},
            status=data.get("status", "draft"),
            description=data.get("description"),
            created_by=created_by,
        )
        db.add(cycle)
        await db.flush()
        return cycle

    async def get_cycle(self, db: AsyncSession, *, organization_id: str, cycle_id: str) -> Optional[PerformanceCycle]:
        return (
            await db.execute(
                select(PerformanceCycle).where(PerformanceCycle.organization_id == organization_id, PerformanceCycle.id == cycle_id)
            )
        ).scalar_one_or_none()

    async def list_cycles(self, db: AsyncSession, *, organization_id: str, status: Optional[str] = None) -> list[PerformanceCycle]:
        query = select(PerformanceCycle).where(PerformanceCycle.organization_id == organization_id)
        if status:
            query = query.where(PerformanceCycle.status == status)
        return (await db.execute(query.order_by(PerformanceCycle.created_at.desc()))).scalars().all()

    async def set_cycle_status(self, db: AsyncSession, *, organization_id: str, cycle_id: str, status: str) -> Optional[PerformanceCycle]:
        if status not in CYCLE_STATUSES:
            raise ValueError(f"invalid cycle status: {status}")
        cycle = await self.get_cycle(db, organization_id=organization_id, cycle_id=cycle_id)
        if cycle is None:
            return None
        cycle.status = status
        await db.flush()
        return cycle

    # ------------------------------------------------------------------ goals

    async def create_goal(self, db: AsyncSession, *, organization_id: str, data: dict[str, Any]) -> PerformanceGoal:
        goal = PerformanceGoal(
            organization_id=organization_id,
            employee_id=data["employee_id"],
            cycle_id=data.get("cycle_id"),
            title=data["title"],
            description=data.get("description"),
            kind=data.get("kind", "project"),
            status=data.get("status", "active"),
            progress=int(data.get("progress", 0)),
            weight=float(data.get("weight", 1.0)),
            due_date=to_date(data.get("due_date")),
        )
        db.add(goal)
        await db.flush()
        return goal

    async def update_goal_progress(self, db: AsyncSession, *, organization_id: str, goal_id: str, progress: int) -> Optional[PerformanceGoal]:
        goal = (
            await db.execute(
                select(PerformanceGoal).where(PerformanceGoal.organization_id == organization_id, PerformanceGoal.id == goal_id)
            )
        ).scalar_one_or_none()
        if goal is None:
            return None
        goal.progress = max(0, min(100, progress))
        if goal.progress >= 100:
            goal.status = "completed"
        elif goal.status == "completed":
            goal.status = "active"
        await db.flush()
        return goal

    async def list_goals(
        self, db: AsyncSession, *, organization_id: str, employee_id: Optional[str] = None,
        cycle_id: Optional[str] = None, status: Optional[str] = None,
    ) -> list[PerformanceGoal]:
        query = select(PerformanceGoal).where(PerformanceGoal.organization_id == organization_id)
        if employee_id:
            query = query.where(PerformanceGoal.employee_id == employee_id)
        if cycle_id:
            query = query.where(PerformanceGoal.cycle_id == cycle_id)
        if status:
            query = query.where(PerformanceGoal.status == status)
        return (await db.execute(query.order_by(PerformanceGoal.created_at.desc()))).scalars().all()

    # ------------------------------------------------------------------ reviews

    async def create_review(self, db: AsyncSession, *, organization_id: str, data: dict[str, Any]) -> PerformanceReview:
        review = PerformanceReview(
            organization_id=organization_id,
            cycle_id=data.get("cycle_id"),
            employee_id=data["employee_id"],
            reviewer_id=data.get("reviewer_id"),
            kind=data.get("kind", "self") if data.get("kind") in REVIEW_KINDS else "self",
        )
        db.add(review)
        await db.flush()
        return review

    async def submit_review(self, db: AsyncSession, *, organization_id: str, review_id: str, data: dict[str, Any]) -> Optional[PerformanceReview]:
        review = (
            await db.execute(
                select(PerformanceReview).where(PerformanceReview.organization_id == organization_id, PerformanceReview.id == review_id)
            )
        ).scalar_one_or_none()
        if review is None or review.status not in ("draft", "submitted"):
            return review
        review.rating = float(data.get("rating", 0.0))
        review.goals = data.get("goals") or review.goals or []
        review.feedback = data.get("feedback")
        review.strengths = data.get("strengths") or []
        review.improvements = data.get("improvements") or []
        review.learning_plan = data.get("learning_plan") or []
        review.status = "submitted"
        review.submitted_at = utcnow()
        await db.flush()
        return review

    async def complete_review(self, db: AsyncSession, *, organization_id: str, review_id: str) -> Optional[PerformanceReview]:
        review = (
            await db.execute(
                select(PerformanceReview).where(PerformanceReview.organization_id == organization_id, PerformanceReview.id == review_id)
            )
        ).scalar_one_or_none()
        if review is None or review.status != "submitted":
            return review
        review.status = "completed"
        review.completed_at = utcnow()
        review.ai_summary = self._ai_summary(review)
        employee = await db.get(Employee, review.employee_id)
        await _event_bus.publish(
            db,
            name="review.completed",
            organization_id=organization_id,
            actor_id=review.reviewer_id or review.employee_id,
            payload={
                "review_id": review.id,
                "employee_id": review.employee_id,
                "employee_name": employee.full_name if employee else None,
                "kind": review.kind,
                "rating": review.rating,
                "cycle_id": review.cycle_id,
            },
            flush=False,
        )
        await db.flush()
        return review

    def _ai_summary(self, review: PerformanceReview) -> str:
        strengths = "; ".join(review.strengths or []) or "no strengths captured"
        improvements = "; ".join(review.improvements or []) or "none noted"
        return (
            f"{review.kind} review scored {review.rating}/5. Strengths: {strengths}. "
            f"Growth areas: {improvements}. Feedback: {(review.feedback or 'n/a')[:400]}"
        )

    async def list_reviews(
        self, db: AsyncSession, *, organization_id: str,
        employee_id: Optional[str] = None, reviewer_id: Optional[str] = None,
        cycle_id: Optional[str] = None, status: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        query = select(PerformanceReview).where(PerformanceReview.organization_id == organization_id)
        if employee_id:
            query = query.where(PerformanceReview.employee_id == employee_id)
        if reviewer_id:
            query = query.where(PerformanceReview.reviewer_id == reviewer_id)
        if cycle_id:
            query = query.where(PerformanceReview.cycle_id == cycle_id)
        if status:
            query = query.where(PerformanceReview.status == status)
        rows = await db.execute(query.order_by(PerformanceReview.created_at.desc()))
        result = []
        for review in rows.scalars().all():
            employee = await db.get(Employee, review.employee_id)
            reviewer = await db.get(Employee, review.reviewer_id) if review.reviewer_id else None
            result.append(
                {
                    "id": review.id,
                    "cycle_id": review.cycle_id,
                    "employee_id": review.employee_id,
                    "employee_name": employee.full_name if employee else None,
                    "reviewer_id": review.reviewer_id,
                    "reviewer_name": reviewer.full_name if reviewer else None,
                    "kind": review.kind,
                    "status": review.status,
                    "rating": review.rating,
                    "feedback": review.feedback,
                    "strengths": review.strengths or [],
                    "improvements": review.improvements or [],
                    "learning_plan": review.learning_plan or [],
                    "ai_summary": review.ai_summary,
                    "submitted_at": review.submitted_at.isoformat() if review.submitted_at else None,
                    "completed_at": review.completed_at.isoformat() if review.completed_at else None,
                }
            )
        return result

    async def employee_summary(self, db: AsyncSession, *, organization_id: str, employee_id: str) -> dict[str, Any]:
        reviews = await self.list_reviews(db, organization_id=organization_id, employee_id=employee_id, status="completed")
        goals = await self.list_goals(db, organization_id=organization_id, employee_id=employee_id)
        ratings = [review["rating"] for review in reviews if review["rating"] > 0]
        return {
            "employee_id": employee_id,
            "reviews": len(reviews),
            "average_rating": round(sum(ratings) / len(ratings), 2) if ratings else 0.0,
            "goals_active": sum(1 for goal in goals if goal.status == "active"),
            "goals_completed": sum(1 for goal in goals if goal.status == "completed"),
            "goal_progress": round(sum(goal.progress for goal in goals) / len(goals)) if goals else 0,
        }

    async def summary(self, db: AsyncSession, *, organization_id: str) -> dict[str, Any]:
        cycles = await self.list_cycles(db, organization_id=organization_id)
        reviews = await self.list_reviews(db, organization_id=organization_id)
        goals = (
            await db.execute(select(PerformanceGoal).where(PerformanceGoal.organization_id == organization_id))
        ).scalars().all()
        ratings = [review["rating"] for review in reviews if review["rating"] > 0]
        return {
            "cycles": {
                "total": len(cycles),
                "open": sum(1 for cycle in cycles if cycle.status == "open"),
                "reviewing": sum(1 for cycle in cycles if cycle.status == "reviewing"),
            },
            "reviews": {
                "total": len(reviews),
                "draft": sum(1 for review in reviews if review["status"] == "draft"),
                "submitted": sum(1 for review in reviews if review["status"] == "submitted"),
                "completed": sum(1 for review in reviews if review["status"] == "completed"),
                "average_rating": round(sum(ratings) / len(ratings), 2) if ratings else 0.0,
            },
            "goals": {
                "total": len(goals),
                "active": sum(1 for goal in goals if goal.status == "active"),
                "completed": sum(1 for goal in goals if goal.status == "completed"),
            },
        }


performance_service = PerformanceService()

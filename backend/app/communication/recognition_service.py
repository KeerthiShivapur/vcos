"""Recognition service (Phase 5.8, 5.15)."""

from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.communication.events import emit_and_audit, notify_user
from app.models.communication import Recognition
from app.models.employee import Employee

BADGE_EMOJIS = {
    "knowledge_expert": "knowledge",
    "mentor": "mentorship",
    "innovator": "innovation",
    "top_collaborator": "teamwork",
    "problem_solver": "helping_others",
    "team_builder": "community",
    "leader": "leadership",
    "community_builder": "community",
    "learning_champion": "learning",
    "project_hero": "customer_success",
}


class RecognitionService:
    async def give(
        self, db: AsyncSession, *, organization_id: str, payload: dict, actor: Employee, ip_address: Optional[str]
    ) -> Recognition:
        recognition = Recognition(
            organization_id=organization_id,
            giver_id=actor.id,
            recipient_id=payload["recipient_id"],
            category=payload["category"],
            message=payload.get("message"),
            badge_code=payload.get("badge_code"),
            public=payload.get("public", True),
        )
        db.add(recognition)
        await db.flush()
        await emit_and_audit(
            db,
            organization_id=organization_id,
            name="recognition.given",
            actor=actor,
            actor_user_id=None,
            ip_address=ip_address,
            payload={
                "recipient_id": recognition.recipient_id,
                "category": recognition.category,
                "badge_code": recognition.badge_code,
            },
            resource_type="recognition",
            resource_id=recognition.id,
        )
        await notify_user(
            db,
            organization_id=organization_id,
            recipient_id=recognition.recipient_id,
            type="community.activity",
            title="You received a recognition",
            body=f"{actor.display_name or actor.first_name} recognized you for {recognition.category.replace('_', ' ')}",
            actor_id=actor.id,
            link="/recognition",
            entity_type="recognition",
            entity_id=recognition.id,
        )
        if recognition.badge_code:
            await self._award_badge(
                db,
                organization_id=organization_id,
                badge_code=recognition.badge_code,
                employee_id=recognition.recipient_id,
                awarded_by=actor.id,
                reason=recognition.message,
            )
        return recognition

    async def _award_badge(
        self, db: AsyncSession, *, organization_id: str, badge_code: str, employee_id: str, awarded_by: Optional[str], reason: Optional[str]
    ) -> None:
        from app.models.communication import Badge, EmployeeBadge

        badge = (
            await db.execute(
                select(Badge).where(
                    Badge.organization_id == organization_id,
                    Badge.code == badge_code,
                )
            )
        ).scalar_one_or_none()
        if badge is None:
            badge = Badge(
                organization_id=organization_id,
                code=badge_code,
                name=badge_code.replace("_", " ").title(),
                category=BADGE_EMOJIS.get(badge_code, "community"),
            )
            db.add(badge)
            await db.flush()
        existing = (
            await db.execute(
                select(EmployeeBadge).where(
                    EmployeeBadge.organization_id == organization_id,
                    EmployeeBadge.badge_id == badge.id,
                    EmployeeBadge.employee_id == employee_id,
                )
            )
        ).scalar_one_or_none()
        if existing is None:
            db.add(
                EmployeeBadge(
                    organization_id=organization_id,
                    badge_id=badge.id,
                    employee_id=employee_id,
                    awarded_by=awarded_by,
                    reason=reason,
                )
            )

    async def get(self, db: AsyncSession, *, organization_id: str, recognition_id: str) -> Optional[Recognition]:
        return (
            await db.execute(
                select(Recognition).where(
                    Recognition.organization_id == organization_id,
                    Recognition.id == recognition_id,
                )
            )
        ).scalar_one_or_none()

    async def list_all(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        employee_id: Optional[str] = None,
        category: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Recognition]:
        filters = [Recognition.organization_id == organization_id, Recognition.public.is_(True)]
        if employee_id:
            filters.append(
                (Recognition.recipient_id == employee_id) | (Recognition.giver_id == employee_id)
            )
        if category:
            filters.append(Recognition.category == category)
        return list(
            (
                await db.execute(
                    select(Recognition)
                    .where(*filters)
                    .order_by(Recognition.created_at.desc())
                    .limit(min(limit, 500))
                    .offset(offset)
                )
            ).scalars().all()
        )

    async def delete(
        self, db: AsyncSession, *, organization_id: str, recognition_id: str, actor: Employee, ip_address: Optional[str]
    ) -> bool:
        recognition = await self.get(db, organization_id=organization_id, recognition_id=recognition_id)
        if recognition is None:
            return False
        await db.delete(recognition)
        await emit_and_audit(
            db,
            organization_id=organization_id,
            name="recognition.deleted",
            actor=actor,
            actor_user_id=None,
            ip_address=ip_address,
            payload={"recognition_id": recognition_id},
            resource_type="recognition",
            resource_id=recognition_id,
        )
        return True

    async def stats(self, db: AsyncSession, *, organization_id: str) -> dict[str, Any]:
        from datetime import datetime, timezone

        total = (
            await db.execute(select(func.count(Recognition.id)).where(Recognition.organization_id == organization_id))
        ).scalar_one()
        month_start = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        month_row = (
            await db.execute(
                select(func.count(Recognition.id)).where(
                    Recognition.organization_id == organization_id,
                    Recognition.created_at >= month_start,
                )
            )
        ).scalar_one()
        month = month_row if month_row is not None else 0
        categories = list(
            (
                await db.execute(
                    select(Recognition.category, func.count(Recognition.id))
                    .where(Recognition.organization_id == organization_id)
                    .group_by(Recognition.category)
                    .order_by(func.count(Recognition.id).desc())
                    .limit(20)
                )
            ).all()
        )
        recipients = list(
            (
                await db.execute(
                    select(Recognition.recipient_id, func.count(Recognition.id))
                    .where(Recognition.organization_id == organization_id)
                    .group_by(Recognition.recipient_id)
                    .order_by(func.count(Recognition.id).desc())
                    .limit(10)
                )
            ).all()
        )
        givers = list(
            (
                await db.execute(
                    select(Recognition.giver_id, func.count(Recognition.id))
                    .where(Recognition.organization_id == organization_id)
                    .group_by(Recognition.giver_id)
                    .order_by(func.count(Recognition.id).desc())
                    .limit(10)
                )
            ).all()
        )
        return {
            "total": total,
            "this_month": month,
            "categories": [{"category": r[0], "count": r[1]} for r in categories],
            "top_recipients": [{"employee_id": r[0], "count": r[1]} for r in recipients],
            "top_givers": [{"employee_id": r[0], "count": r[1]} for r in givers],
        }


recognition_service = RecognitionService()

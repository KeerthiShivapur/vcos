"""Badge / gamification service (Phase 5.15)."""

from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.communication import Badge, EmployeeBadge

BADGE_CATALOG = {
    "knowledge_expert": ("Knowledge Expert", "Sharing deep expertise in the knowledge base", "knowledge"),
    "mentor": ("Mentor", "Guiding and developing colleagues", "mentorship"),
    "innovator": ("Innovator", "Driving new ideas in the innovation hub", "innovation"),
    "top_collaborator": ("Top Collaborator", "Highly collaborative and engaged", "teamwork"),
    "problem_solver": ("Problem Solver", "Helping others in forums and comments", "helping_others"),
    "community_builder": ("Community Builder", "Building strong communities", "community"),
    "leader": ("Leader", "Demonstrating exceptional leadership", "leadership"),
    "learning_champion": ("Learning Champion", "Commitment to continuous learning", "learning"),
    "project_hero": ("Project Hero", "Outstanding project contribution", "customer_success"),
    "event_star": ("Event Star", "Active at community events and clubs", "community"),
}


class BadgeService:
    async def sync_catalog(self, db: AsyncSession, *, organization_id: str) -> int:
        """Ensure every catalog badge exists for the org; return created count."""
        existing = {
            row[0]
            for row in (
                await db.execute(select(Badge.code).where(Badge.organization_id == organization_id))
            ).all()
        }
        created = 0
        for code, (name, description, category) in BADGE_CATALOG.items():
            if code not in existing:
                db.add(
                    Badge(
                        organization_id=organization_id,
                        code=code,
                        name=name,
                        description=description,
                        icon=code,
                        category=category,
                    )
                )
                created += 1
        return created

    async def list_badges(self, db: AsyncSession, *, organization_id: str) -> list[Badge]:
        return list(
            (
                await db.execute(
                    select(Badge).where(Badge.organization_id == organization_id).order_by(Badge.name.asc())
                )
            ).scalars().all()
        )

    async def employee_badges(self, db: AsyncSession, *, organization_id: str, employee_id: str) -> list[EmployeeBadge]:
        return list(
            (
                await db.execute(
                    select(EmployeeBadge)
                    .where(
                        EmployeeBadge.organization_id == organization_id,
                        EmployeeBadge.employee_id == employee_id,
                    )
                    .order_by(EmployeeBadge.created_at.desc())
                )
            ).scalars().all()
        )

    async def all_employee_badges(self, db: AsyncSession, *, organization_id: str) -> list[EmployeeBadge]:
        return list(
            (
                await db.execute(
                    select(EmployeeBadge)
                    .where(EmployeeBadge.organization_id == organization_id)
                    .order_by(EmployeeBadge.created_at.desc())
                )
            ).scalars().all()
        )

    async def leaderboard(self, db: AsyncSession, *, organization_id: str, limit: int = 20) -> list[dict]:
        rows = (
            await db.execute(
                select(EmployeeBadge.employee_id, func.count(EmployeeBadge.id))
                .where(EmployeeBadge.organization_id == organization_id)
                .group_by(EmployeeBadge.employee_id)
                .order_by(func.count(EmployeeBadge.id).desc())
                .limit(min(limit, 100))
            )
        ).all()
        return [{"employee_id": employee_id, "badge_count": count} for employee_id, count in rows]


badge_service = BadgeService()

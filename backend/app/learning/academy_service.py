"""Academy service (Phase 10.8 — Internal Academy).

Organizations create learning academies (Engineering, Leadership, Sales,
Security, AI, Finance, ...). Academies group courses and members behind a
shared theme; members see their academy's courses and the academy's expert
community.
"""

import logging
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.academy import Academy, AcademyCourse, AcademyMember
from app.models.course import Course

logger = logging.getLogger("vcos.learning.academies")


class AcademyService:
    async def create(self, db: AsyncSession, *, organization_id: str, data: dict[str, Any]) -> Academy:
        academy = Academy(
            organization_id=organization_id,
            name=data["name"],
            description=data.get("description"),
            category=data.get("category"),
            cover_url=data.get("cover_url"),
            curriculum=data.get("curriculum") or [],
            status=data.get("status", "published"),
        )
        db.add(academy)
        await db.flush()
        return academy

    async def get(self, db: AsyncSession, *, organization_id: str, academy_id: str) -> Optional[Academy]:
        return (
            await db.execute(
                select(Academy)
                .options(selectinload(Academy.members), selectinload(Academy.courses))
                .where(
                    Academy.organization_id == organization_id, Academy.id == academy_id
                )
            )
        ).scalar_one_or_none()

    async def list_academies(self, db: AsyncSession, *, organization_id: str, category: Optional[str] = None, status: str = "published") -> list[Academy]:
        query = select(Academy).where(Academy.organization_id == organization_id)
        if status:
            query = query.where(Academy.status == status)
        if category:
            query = query.where(Academy.category == category)
        query = query.options(selectinload(Academy.members), selectinload(Academy.courses))
        return (await db.execute(query.order_by(Academy.name))).scalars().all()

    async def add_course(self, db: AsyncSession, *, organization_id: str, academy_id: str, course_id: str) -> Optional[AcademyCourse]:
        academy = await self.get(db, organization_id=organization_id, academy_id=academy_id)
        if academy is None:
            return None
        existing = (
            await db.execute(
                select(AcademyCourse).where(
                    AcademyCourse.organization_id == organization_id,
                    AcademyCourse.academy_id == academy_id,
                    AcademyCourse.course_id == course_id,
                )
            )
        ).scalar_one_or_none()
        if existing:
            return existing
        position = (
            (
                await db.execute(
                    select(func.max(AcademyCourse.position)).where(
                        AcademyCourse.organization_id == organization_id,
                        AcademyCourse.academy_id == academy_id,
                    )
                )
            ).scalar()
            or 0
        ) + 1
        link = AcademyCourse(
            organization_id=organization_id, academy_id=academy_id,
            course_id=course_id, position=position,
        )
        db.add(link)
        await db.flush()
        return link

    async def remove_course(self, db: AsyncSession, *, organization_id: str, academy_id: str, course_id: str) -> bool:
        link = (
            await db.execute(
                select(AcademyCourse).where(
                    AcademyCourse.organization_id == organization_id,
                    AcademyCourse.academy_id == academy_id,
                    AcademyCourse.course_id == course_id,
                )
            )
        ).scalar_one_or_none()
        if link is None:
            return False
        await db.delete(link)
        await db.flush()
        return True

    async def join(self, db: AsyncSession, *, organization_id: str, academy_id: str, employee_id: str) -> Optional[AcademyMember]:
        academy = await self.get(db, organization_id=organization_id, academy_id=academy_id)
        if academy is None:
            return None
        existing = (
            await db.execute(
                select(AcademyMember).where(
                    AcademyMember.organization_id == organization_id,
                    AcademyMember.academy_id == academy_id,
                    AcademyMember.employee_id == employee_id,
                )
            )
        ).scalar_one_or_none()
        if existing:
            return existing
        member = AcademyMember(
            organization_id=organization_id, academy_id=academy_id,
            employee_id=employee_id, role="member",
        )
        db.add(member)
        await db.flush()
        return member

    async def leave(self, db: AsyncSession, *, organization_id: str, academy_id: str, employee_id: str) -> bool:
        member = (
            await db.execute(
                select(AcademyMember).where(
                    AcademyMember.organization_id == organization_id,
                    AcademyMember.academy_id == academy_id,
                    AcademyMember.employee_id == employee_id,
                )
            )
        ).scalar_one_or_none()
        if member is None:
            return False
        await db.delete(member)
        await db.flush()
        return True

    async def courses(self, db: AsyncSession, *, organization_id: str, academy_id: str) -> list[Course]:
        rows = await db.execute(
            select(Course)
            .join(AcademyCourse, AcademyCourse.course_id == Course.id)
            .where(
                AcademyCourse.organization_id == organization_id,
                AcademyCourse.academy_id == academy_id,
            )
            .order_by(AcademyCourse.position)
        )
        return rows.scalars().all()

    async def my_academies(self, db: AsyncSession, *, organization_id: str, employee_id: str) -> list[dict[str, Any]]:
        rows = await db.execute(
            select(Academy)
            .join(AcademyMember, AcademyMember.academy_id == Academy.id)
            .where(
                AcademyMember.organization_id == organization_id,
                AcademyMember.employee_id == employee_id,
                Academy.status == "published",
            )
            .order_by(Academy.name)
        )
        return [
            {
                "id": academy.id,
                "name": academy.name,
                "description": academy.description,
                "category": academy.category,
                "cover_url": academy.cover_url,
                "course_count": len(await self.courses(db, organization_id=organization_id, academy_id=academy.id)),
                "member_count": (
                    (
                        await db.execute(
                            select(func.count(AcademyMember.id)).where(
                                AcademyMember.organization_id == organization_id,
                                AcademyMember.academy_id == academy.id,
                            )
                        )
                    ).scalar()
                    or 0
                ),
            }
            for academy in rows.scalars().all()
        ]


academy_service = AcademyService()

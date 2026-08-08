"""Community service — communities and membership (Phase 5.1, 5.7, 5.12)."""

import uuid
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.communication.events import emit_and_audit, notify_community_members
from app.models.communication import Community, CommunityMember
from app.models.employee import Employee

DEFAULT_ROLE = "member"


def slugify(name: str) -> str:
    base = "".join(ch if ch.isalnum() else "-" for ch in name.lower()).strip("-")
    return (base or "community")[:120]


class CommunityService:
    async def create(
        self, db: AsyncSession, *, organization_id: str, payload: dict, actor: Optional[Employee], ip_address: Optional[str]
    ) -> Community:
        name = payload["name"]
        community = Community(
            organization_id=organization_id,
            name=name,
            slug=await self._unique_slug(db, organization_id, slugify(name)),
            description=payload.get("description"),
            type=payload.get("type", "general"),
            visibility=payload.get("visibility", "public"),
            icon=payload.get("icon"),
            banner=payload.get("banner"),
            owner_id=actor.id if actor else None,
            member_count=1 if actor else 0,
        )
        db.add(community)
        await db.flush()
        if actor:
            db.add(
                CommunityMember(
                    organization_id=organization_id,
                    community_id=community.id,
                    employee_id=actor.id,
                    role="owner",
                    joined_at=community.created_at,
                )
            )
        await emit_and_audit(
            db,
            organization_id=organization_id,
            name="community.created",
            actor=actor,
            actor_user_id=None,
            ip_address=ip_address,
            payload={"community_id": community.id, "name": community.name},
            resource_type="community",
            resource_id=community.id,
        )
        return community

    async def _unique_slug(self, db: AsyncSession, organization_id: str, base: str) -> str:
        candidate = base
        for _ in range(50):
            exists = (
                await db.execute(
                    select(Community.id).where(
                        Community.organization_id == organization_id,
                        Community.slug == candidate,
                    )
                )
            ).scalar_one_or_none()
            if not exists:
                return candidate
            candidate = f"{base}-{uuid.uuid4().hex[:6]}"
        return f"{base}-{uuid.uuid4().hex[:8]}"

    async def get(self, db: AsyncSession, *, organization_id: str, community_id: str) -> Optional[Community]:
        return (
            await db.execute(
                select(Community).where(
                    Community.organization_id == organization_id,
                    Community.id == community_id,
                )
            )
        ).scalar_one_or_none()

    async def list_all(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        type: Optional[str] = None,
        search: Optional[str] = None,
        mine_only: bool = False,
        employee_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Community]:
        filters = [Community.organization_id == organization_id, Community.is_archived.is_(False)]
        if type:
            filters.append(Community.type == type)
        if search:
            filters.append(func.lower(Community.name).like(f"%{search.lower()}%"))
        if mine_only and employee_id:
            filters.append(Community.id.in_(select(CommunityMember.community_id).where(CommunityMember.employee_id == employee_id)))
        return list(
            (
                await db.execute(
                    select(Community)
                    .where(*filters)
                    .order_by(Community.member_count.desc(), Community.created_at.desc())
                    .limit(min(limit, 500))
                    .offset(offset)
                )
            ).scalars().all()
        )

    async def update(
        self, db: AsyncSession, *, organization_id: str, community_id: str, payload: dict, actor: Optional[Employee], ip_address: Optional[str]
    ) -> Optional[Community]:
        community = await self.get(db, organization_id=organization_id, community_id=community_id)
        if community is None:
            return None
        for key, value in payload.items():
            if value is not None and hasattr(community, key):
                setattr(community, key, value)
        if "name" in payload and payload["name"]:
            community.slug = await self._unique_slug(db, organization_id, slugify(community.name))
        await emit_and_audit(
            db,
            organization_id=organization_id,
            name="community.updated",
            actor=actor,
            actor_user_id=None,
            ip_address=ip_address,
            payload={"community_id": community.id},
            resource_type="community",
            resource_id=community.id,
        )
        return community

    async def delete(
        self, db: AsyncSession, *, organization_id: str, community_id: str, actor: Optional[Employee], ip_address: Optional[str]
    ) -> bool:
        community = await self.get(db, organization_id=organization_id, community_id=community_id)
        if community is None:
            return False
        await db.delete(community)
        await emit_and_audit(
            db,
            organization_id=organization_id,
            name="community.deleted",
            actor=actor,
            actor_user_id=None,
            ip_address=ip_address,
            payload={"community_id": community_id},
            resource_type="community",
            resource_id=community_id,
        )
        return True

    # ------------------------------------------------------------- membership

    async def membership(
        self, db: AsyncSession, *, organization_id: str, community_id: str, employee_id: str
    ) -> Optional[CommunityMember]:
        return (
            await db.execute(
                select(CommunityMember).where(
                    CommunityMember.organization_id == organization_id,
                    CommunityMember.community_id == community_id,
                    CommunityMember.employee_id == employee_id,
                )
            )
        ).scalar_one_or_none()

    async def is_member(self, db: AsyncSession, *, organization_id: str, community_id: str, employee_id: str) -> bool:
        return await self.membership(db, organization_id=organization_id, community_id=community_id, employee_id=employee_id) is not None

    async def join(
        self, db: AsyncSession, *, organization_id: str, community_id: str, actor: Employee, ip_address: Optional[str]
    ) -> tuple[Community, CommunityMember]:
        community = await self.get(db, organization_id=organization_id, community_id=community_id)
        if community is None:
            raise ValueError("Community not found")
        member = await self.membership(db, organization_id=organization_id, community_id=community_id, employee_id=actor.id)
        if member is None:
            member = CommunityMember(
                organization_id=organization_id,
                community_id=community_id,
                employee_id=actor.id,
                role=DEFAULT_ROLE,
            )
            db.add(member)
            community.member_count = (community.member_count or 0) + 1
            await emit_and_audit(
                db,
                organization_id=organization_id,
                name="community.joined",
                actor=actor,
                actor_user_id=None,
                ip_address=ip_address,
                payload={"community_id": community_id},
                resource_type="community",
                resource_id=community_id,
            )
        return community, member

    async def leave(
        self, db: AsyncSession, *, organization_id: str, community_id: str, actor: Employee, ip_address: Optional[str]
    ) -> bool:
        member = await self.membership(db, organization_id=organization_id, community_id=community_id, employee_id=actor.id)
        if member is None:
            return False
        community = await self.get(db, organization_id=organization_id, community_id=community_id)
        await db.delete(member)
        if community is not None:
            community.member_count = max(0, (community.member_count or 1) - 1)
        await emit_and_audit(
            db,
            organization_id=organization_id,
            name="community.left",
            actor=actor,
            actor_user_id=None,
            ip_address=ip_address,
            payload={"community_id": community_id},
            resource_type="community",
            resource_id=community_id,
        )
        return True

    async def set_role(
        self, db: AsyncSession, *, organization_id: str, community_id: str, employee_id: str, role: str, actor: Optional[Employee], ip_address: Optional[str]
    ) -> Optional[CommunityMember]:
        member = await self.membership(db, organization_id=organization_id, community_id=community_id, employee_id=employee_id)
        if member is None:
            return None
        member.role = role
        await emit_and_audit(
            db,
            organization_id=organization_id,
            name="community.member_role",
            actor=actor,
            actor_user_id=None,
            ip_address=ip_address,
            payload={"community_id": community_id, "employee_id": employee_id, "role": role},
            resource_type="community",
            resource_id=community_id,
        )
        return member

    async def members(
        self, db: AsyncSession, *, organization_id: str, community_id: str, limit: int = 100, offset: int = 0
    ) -> list[CommunityMember]:
        return list(
            (
                await db.execute(
                    select(CommunityMember)
                    .where(
                        CommunityMember.organization_id == organization_id,
                        CommunityMember.community_id == community_id,
                    )
                    .order_by(CommunityMember.joined_at.asc())
                    .limit(min(limit, 500))
                    .offset(offset)
                )
            ).scalars().all()
        )

    async def member_count(self, db: AsyncSession, *, organization_id: str, community_id: str) -> int:
        return (
            await db.execute(
                select(func.count(CommunityMember.id)).where(
                    CommunityMember.organization_id == organization_id,
                    CommunityMember.community_id == community_id,
                )
            )
        ).scalar_one()

    async def touch_last_seen(
        self, db: AsyncSession, *, organization_id: str, community_id: str, employee_id: str, seen_at: Any
    ) -> None:
        member = await self.membership(db, organization_id=organization_id, community_id=community_id, employee_id=employee_id)
        if member is not None:
            member.last_seen = seen_at

    async def notify_members(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        community_id: str,
        type: str,
        title: str,
        body: Optional[str] = None,
        actor_id: Optional[str] = None,
        link: Optional[str] = None,
        entity_type: Optional[str] = None,
        entity_id: Optional[str] = None,
    ) -> int:
        return await notify_community_members(
            db,
            organization_id=organization_id,
            community_id=community_id,
            type=type,
            title=title,
            body=body,
            actor_id=actor_id,
            link=link,
            entity_type=entity_type,
            entity_id=entity_id,
        )


community_service = CommunityService()

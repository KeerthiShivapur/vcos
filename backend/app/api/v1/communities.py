"""Communities API (Phase 5.1, 5.7, 5.12)."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_client_ip, get_current_organization, require_permission
from app.communication.community_service import community_service
from app.communication.presenters import present_community, present_member, _names
from app.db.database import get_db
from app.models.employee import Employee
from app.models.organization import Organization
from app.models.user import User
from app.schemas.common import Message
from app.schemas.communication import CommunityCreate, CommunityRolePayload, CommunityUpdate

router = APIRouter(prefix="/communities", tags=["Communities"])


async def _actor(db: AsyncSession, org: Organization, user: User):
    from app.people.employee_service import employee_service

    return await employee_service.get_by_user(db, organization_id=org.id, user_id=user.id)


async def _require_community(db: AsyncSession, org: Organization, community_id: str):
    community = await community_service.get(db, organization_id=org.id, community_id=community_id)
    if community is None:
        raise HTTPException(404, "Community not found")
    return community


@router.get("/analytics", response_model=dict)
async def community_analytics(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("communication:read")),
    db: AsyncSession = Depends(get_db),
):
    from app.communication.analytics_service import analytics_service

    overview = await analytics_service.overview(db, organization_id=org.id)
    top = await analytics_service.top_communities(db, organization_id=org.id, limit=10)
    contributors = await analytics_service.top_contributors(db, organization_id=org.id, limit=10)
    trend = await analytics_service.activity_trend(db, organization_id=org.id, days=30)
    return {"overview": overview, "top_communities": top, "top_contributors": contributors, "activity_trend": trend}


@router.get("", response_model=list[dict])
async def list_communities(
    type: Optional[str] = None,
    search: Optional[str] = None,
    mine_only: bool = False,
    limit: int = 100,
    offset: int = 0,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("communication:read")),
    db: AsyncSession = Depends(get_db),
):
    actor = await _actor(db, org, user)
    communities = await community_service.list_all(
        db,
        organization_id=org.id,
        type=type,
        search=search,
        mine_only=mine_only,
        employee_id=actor.id if actor else None,
        limit=min(limit, 500),
        offset=offset,
    )
    my_memberships: dict[str, str] = {}
    if actor:
        from app.models.communication import CommunityMember

        rows = (
            await db.execute(
                select(CommunityMember.community_id, CommunityMember.role).where(
                    CommunityMember.organization_id == org.id,
                    CommunityMember.employee_id == actor.id,
                )
            )
        ).all()
        my_memberships = {row[0]: row[1] for row in rows}
    return [
        await present_community(
            c, is_member=c.id in my_memberships, my_role=my_memberships.get(c.id)
        )
        for c in communities
    ]


@router.post("", response_model=dict, status_code=201)
async def create_community(
    payload: CommunityCreate,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("communication:manage")),
    db: AsyncSession = Depends(get_db),
):
    actor = await _actor(db, org, user)
    community = await community_service.create(
        db, organization_id=org.id, payload=payload.model_dump(), actor=actor, ip_address=get_client_ip(request)
    )
    await db.commit()
    return await present_community(community, is_member=True, my_role="owner")


@router.get("/{community_id}", response_model=dict)
async def get_community(
    community_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("communication:read")),
    db: AsyncSession = Depends(get_db),
):
    community = await _require_community(db, org, community_id)
    actor = await _actor(db, org, user)
    is_member = False
    my_role = None
    if actor:
        membership = await community_service.membership(db, organization_id=org.id, community_id=community_id, employee_id=actor.id)
        is_member = membership is not None
        my_role = membership.role if membership else None
    return await present_community(community, is_member=is_member, my_role=my_role)


@router.patch("/{community_id}", response_model=dict)
async def update_community(
    community_id: str,
    payload: CommunityUpdate,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("communication:manage")),
    db: AsyncSession = Depends(get_db),
):
    await _require_community(db, org, community_id)
    actor = await _actor(db, org, user)
    community = await community_service.update(
        db, organization_id=org.id, community_id=community_id, payload=payload.model_dump(exclude_unset=True),
        actor=actor, ip_address=get_client_ip(request),
    )
    await db.commit()
    return await present_community(community)


@router.delete("/{community_id}", response_model=Message)
async def delete_community(
    community_id: str,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("communication:manage")),
    db: AsyncSession = Depends(get_db),
):
    await _require_community(db, org, community_id)
    actor = await _actor(db, org, user)
    await community_service.delete(
        db, organization_id=org.id, community_id=community_id, actor=actor, ip_address=get_client_ip(request)
    )
    await db.commit()
    return Message(message="Community deleted")


@router.post("/{community_id}/join", response_model=dict)
async def join_community(
    community_id: str,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("communication:read")),
    db: AsyncSession = Depends(get_db),
):
    await _require_community(db, org, community_id)
    actor = await _actor(db, org, user)
    if actor is None:
        raise HTTPException(400, "No employee profile linked")
    community, _ = await community_service.join(
        db, organization_id=org.id, community_id=community_id, actor=actor, ip_address=get_client_ip(request)
    )
    await db.commit()
    return await present_community(community, is_member=True, my_role="member")


@router.post("/{community_id}/leave", response_model=Message)
async def leave_community(
    community_id: str,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("communication:read")),
    db: AsyncSession = Depends(get_db),
):
    actor = await _actor(db, org, user)
    if actor is None:
        raise HTTPException(400, "No employee profile linked")
    if not await community_service.leave(
        db, organization_id=org.id, community_id=community_id, actor=actor, ip_address=get_client_ip(request)
    ):
        raise HTTPException(404, "Membership not found")
    await db.commit()
    return Message(message="Left community")


@router.post("/{community_id}/role", response_model=dict)
async def set_member_role(
    community_id: str,
    payload: CommunityRolePayload,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("communication:manage")),
    db: AsyncSession = Depends(get_db),
):
    await _require_community(db, org, community_id)
    actor = await _actor(db, org, user)
    member = await community_service.set_role(
        db, organization_id=org.id, community_id=community_id, employee_id=payload.employee_id,
        role=payload.role, actor=actor, ip_address=get_client_ip(request),
    )
    if member is None:
        raise HTTPException(404, "Member not found")
    await db.commit()
    return {"employee_id": member.employee_id, "role": member.role}


@router.get("/{community_id}/members", response_model=list[dict])
async def list_members(
    community_id: str,
    limit: int = 100,
    offset: int = 0,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("communication:read")),
    db: AsyncSession = Depends(get_db),
):
    await _require_community(db, org, community_id)
    members = await community_service.members(
        db, organization_id=org.id, community_id=community_id, limit=min(limit, 500), offset=offset
    )
    names = await _names(db, [m.employee_id for m in members])
    return [await present_member(m, employee_name=names.get(m.employee_id)) for m in members]

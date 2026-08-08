"""Organization endpoints: profile, settings, branding, stats."""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_client_ip, get_current_organization, get_current_user, require_permission
from app.models.organization import Organization
from app.models.user import User
from app.schemas.common import Message
from app.schemas.organization import (
    OrganizationBranding,
    OrganizationOut,
    OrganizationSettingsOut,
    OrganizationSettingsUpdate,
    OrganizationStats,
    OrganizationUpdate,
)
from app.db.database import get_db
from app.services.audit_service import audit_service
from app.services.organization_service import organization_service

router = APIRouter(prefix="/organizations", tags=["Organizations"])


@router.get("/me", response_model=OrganizationOut)
async def get_my_organization(org: Organization = Depends(get_current_organization)):
    return OrganizationOut.model_validate(org)


@router.patch("/me", response_model=OrganizationOut)
async def update_my_organization(
    payload: OrganizationUpdate,
    request: Request,
    user: User = Depends(require_permission("organization:update")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    data = payload.model_dump(exclude_unset=True)
    org = await organization_service.update(
        db,
        org,
        data,
        actor_id=user.id,
        actor_email=user.email,
        ip_address=get_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    await db.commit()
    return OrganizationOut.model_validate(org)


@router.post("/me/branding", response_model=OrganizationOut)
async def update_branding(
    payload: OrganizationBranding,
    request: Request,
    user: User = Depends(require_permission("organization:update")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    data = payload.model_dump(exclude_unset=True)
    org = await organization_service.update(
        db,
        org,
        data,
        actor_id=user.id,
        actor_email=user.email,
        ip_address=get_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    await audit_service.log(
        db,
        organization_id=org.id,
        action="organization.branding.updated",
        actor_id=user.id,
        actor_email=user.email,
        ip_address=get_client_ip(request),
    )
    await db.commit()
    return OrganizationOut.model_validate(org)


@router.get("/me/settings", response_model=OrganizationSettingsOut)
async def get_org_settings(
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    settings = await organization_service.get_settings(db, org.id)
    return OrganizationSettingsOut.model_validate(settings)


@router.patch("/me/settings", response_model=OrganizationSettingsOut)
async def update_org_settings(
    payload: OrganizationSettingsUpdate,
    user: User = Depends(require_permission("organization:settings")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    settings = await organization_service.update_settings(
        db, org.id, payload.model_dump(exclude_unset=True), actor_id=user.id, actor_email=user.email
    )
    await db.commit()
    return OrganizationSettingsOut.model_validate(settings)


@router.get("/me/stats", response_model=OrganizationStats)
async def org_stats(
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    return OrganizationStats(**await organization_service.stats(db, org.id))

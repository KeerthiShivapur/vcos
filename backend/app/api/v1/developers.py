"""Phase 18 — Developer Ecosystem API: portal, applications, API keys,
usage analytics, billing and certifications."""

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_organization, get_current_user, require_permission
from app.db.database import get_db
from app.developers.analytics_service import developer_analytics_service
from app.developers.application_service import developer_application_service
from app.developers.billing_service import developer_billing_service
from app.developers.certification_service import certification_service
from app.developers.portal_service import developer_portal_service
from app.models.organization import Organization
from app.models.user import User

router = APIRouter(prefix="/developers", tags=["developers"])


class DeveloperRegisterIn(BaseModel):
    name: str
    email: str
    bio: Optional[str] = None
    website: Optional[str] = None
    country: Optional[str] = None


class ApplicationCreateIn(BaseModel):
    name: str
    app_type: str = "app"
    description: Optional[str] = None
    scopes: Optional[list[str]] = None
    endpoints: Optional[dict[str, Any]] = None
    settings: Optional[dict[str, Any]] = None


class ApplicationUpdateIn(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    version: Optional[str] = None
    scopes: Optional[list[str]] = None
    endpoints: Optional[dict[str, Any]] = None
    settings: Optional[dict[str, Any]] = None


class ApiKeyCreateIn(BaseModel):
    name: str
    scopes: Optional[list[str]] = None
    rate_limit_per_minute: int = 60


class UsageRecordIn(BaseModel):
    application_id: str
    usage_date: str
    unit: str
    value: float


class PlanChangeIn(BaseModel):
    plan: str


class CertificationAttemptIn(BaseModel):
    exam: str
    score: float


def _resolve_developer(db: AsyncSession, user: User, org: Organization) -> dict[str, Any]:
    raise RuntimeError("unreachable")


@router.post("/register")
async def register_developer(
    body: DeveloperRegisterIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    developer = await developer_portal_service.register(
        db,
        user_id=user.id,
        name=body.name,
        email=body.email,
        bio=body.bio,
        website=body.website,
        country=body.country,
        organization_id=user.organization_id,
    )
    await db.commit()
    return developer


@router.get("/me")
async def my_profile(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    developer = await developer_portal_service.find_by_user(db, user.id)
    if developer is None:
        raise HTTPException(status_code=404, detail="developer not registered")
    profile = developer_portal_service.serialize(developer)
    subscription = await developer_billing_service.ensure(db, developer.id)
    return {"profile": profile, "subscription": subscription}


@router.get("")
async def list_developers(
    limit: int = Query(default=100, ge=1, le=200),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("developers:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    rows = await developer_portal_service.list(db, limit=limit)
    return {"total": len(rows), "developers": rows}


@router.post("/{developer_id}/verify")
async def verify_developer(
    developer_id: str,
    verified: bool = True,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("developers:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    row = await developer_portal_service.set_verified(db, developer_id, verified=verified)
    if row is None:
        raise HTTPException(status_code=404, detail="developer not found")
    await db.commit()
    return row


# ------------------------------------------------------------------ applications

@router.get("/me/applications")
async def my_applications(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    developer = await developer_portal_service.find_by_user(db, user.id)
    if developer is None:
        raise HTTPException(status_code=404, detail="developer not registered")
    rows = await developer_application_service.list(db, developer.id)
    return {"total": len(rows), "applications": rows}


@router.post("/me/applications")
async def create_application(
    body: ApplicationCreateIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    developer = await developer_portal_service.find_by_user(db, user.id)
    if developer is None:
        raise HTTPException(status_code=404, detail="developer not registered")
    try:
        row = await developer_application_service.create(
            db,
            developer_id=developer.id,
            name=body.name,
            app_type=body.app_type,
            description=body.description,
            scopes=body.scopes,
            endpoints=body.endpoints,
            settings=body.settings,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    await db.commit()
    return row


@router.patch("/me/applications/{application_id}")
async def update_application(
    application_id: str,
    body: ApplicationUpdateIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    developer = await developer_portal_service.find_by_user(db, user.id)
    if developer is None:
        raise HTTPException(status_code=404, detail="developer not registered")
    row = await developer_application_service.update(
        db, developer.id, application_id,
        name=body.name, description=body.description, version=body.version,
        scopes=body.scopes, endpoints=body.endpoints, settings=body.settings,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="application not found")
    await db.commit()
    return row


@router.post("/me/applications/{application_id}/publish")
async def publish_application(
    application_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    developer = await developer_portal_service.find_by_user(db, user.id)
    if developer is None:
        raise HTTPException(status_code=404, detail="developer not registered")
    row = await developer_application_service.publish(
        db, developer.id, application_id, organization_id=user.organization_id
    )
    if row is None:
        raise HTTPException(status_code=404, detail="application not found")
    await db.commit()
    return row


@router.post("/me/applications/{application_id}/delist")
async def delist_application(
    application_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    developer = await developer_portal_service.find_by_user(db, user.id)
    if developer is None:
        raise HTTPException(status_code=404, detail="developer not registered")
    row = await developer_application_service.delist(
        db, developer.id, application_id, organization_id=user.organization_id
    )
    if row is None:
        raise HTTPException(status_code=404, detail="application not found")
    await db.commit()
    return row


# --------------------------------------------------------------------- API keys

@router.post("/me/applications/{application_id}/keys")
async def create_api_key(
    application_id: str,
    body: ApiKeyCreateIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    developer = await developer_portal_service.find_by_user(db, user.id)
    if developer is None:
        raise HTTPException(status_code=404, detail="developer not registered")
    row = await developer_application_service.create_key(
        db,
        developer_id=developer.id,
        application_id=application_id,
        name=body.name,
        scopes=body.scopes,
        rate_limit_per_minute=body.rate_limit_per_minute,
        organization_id=user.organization_id,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="application not found")
    await db.commit()
    return row


@router.get("/me/applications/{application_id}/keys")
async def list_api_keys(
    application_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    developer = await developer_portal_service.find_by_user(db, user.id)
    if developer is None:
        raise HTTPException(status_code=404, detail="developer not registered")
    rows = await developer_application_service.list_keys(db, developer.id, application_id)
    return {"total": len(rows), "keys": rows}


@router.post("/me/keys/{key_id}/revoke")
async def revoke_api_key(
    key_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    developer = await developer_portal_service.find_by_user(db, user.id)
    if developer is None:
        raise HTTPException(status_code=404, detail="developer not registered")
    row = await developer_application_service.revoke_key(
        db, developer.id, key_id, organization_id=user.organization_id
    )
    if row is None:
        raise HTTPException(status_code=404, detail="key not found")
    await db.commit()
    return row


# ------------------------------------------------------------------- analytics

@router.get("/me/analytics")
async def my_analytics(
    days: int = Query(default=30, ge=1, le=365),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    developer = await developer_portal_service.find_by_user(db, user.id)
    if developer is None:
        raise HTTPException(status_code=404, detail="developer not registered")
    return await developer_analytics_service.summary(db, developer.id, days=days)


@router.post("/usage/record")
async def record_usage(
    body: UsageRecordIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    developer = await developer_portal_service.find_by_user(db, user.id)
    if developer is None:
        raise HTTPException(status_code=404, detail="developer not registered")
    try:
        row = await developer_analytics_service.record(
            db,
            developer_id=developer.id,
            application_id=body.application_id,
            usage_date=body.usage_date,
            unit=body.unit,
            value=body.value,
            organization_id=user.organization_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    await db.commit()
    return row


# -------------------------------------------------------------------- billing

@router.get("/me/subscription")
async def my_subscription(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    developer = await developer_portal_service.find_by_user(db, user.id)
    if developer is None:
        raise HTTPException(status_code=404, detail="developer not registered")
    return await developer_billing_service.ensure(db, developer.id)


@router.post("/me/subscription/plan")
async def change_plan(
    body: PlanChangeIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    developer = await developer_portal_service.find_by_user(db, user.id)
    if developer is None:
        raise HTTPException(status_code=404, detail="developer not registered")
    try:
        row = await developer_billing_service.change_plan(
            db, developer.id, body.plan, organization_id=user.organization_id
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    await db.commit()
    return row


# --------------------------------------------------------------- certifications

@router.post("/me/certifications/attempt")
async def attempt_certification(
    body: CertificationAttemptIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    developer = await developer_portal_service.find_by_user(db, user.id)
    if developer is None:
        raise HTTPException(status_code=404, detail="developer not registered")
    try:
        row = await certification_service.attempt(
            db,
            developer_id=developer.id,
            exam=body.exam,
            score=body.score,
            organization_id=user.organization_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    await db.commit()
    return row


@router.get("/me/certifications")
async def my_certifications(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    developer = await developer_portal_service.find_by_user(db, user.id)
    if developer is None:
        raise HTTPException(status_code=404, detail="developer not registered")
    rows = await certification_service.credentials(db, developer.id)
    return {"total": len(rows), "certifications": rows}

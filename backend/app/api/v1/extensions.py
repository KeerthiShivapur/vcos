"""Phase 18 — Extension marketplace & themes API: listings, installs,
reviews, and organization branding themes."""

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_organization, get_current_user, require_permission
from app.db.database import get_db
from app.developers.marketplace_service import extension_marketplace_service
from app.developers.portal_service import developer_portal_service
from app.developers.theme_service import theme_service
from app.models.organization import Organization
from app.models.user import User

router = APIRouter(prefix="/marketplace", tags=["marketplace"])
theme_router = APIRouter(prefix="/themes", tags=["themes"])


class ListingCreateIn(BaseModel):
    application_id: str
    name: str
    description: Optional[str] = None
    category: str = "general"
    price: float = 0.0


class InstallIn(BaseModel):
    item_id: str
    as_agent: bool = False


class ReviewIn(BaseModel):
    item_id: str
    rating: int
    comment: Optional[str] = None


class ThemeCreateIn(BaseModel):
    name: str
    config: Optional[dict[str, Any]] = None
    source: str = "custom"
    activate: bool = False


class ThemeUpdateIn(BaseModel):
    name: Optional[str] = None
    config: Optional[dict[str, Any]] = None


async def _developer_id(db: AsyncSession, user: User) -> Optional[str]:
    developer = await developer_portal_service.find_by_user(db, user.id)
    return developer.id if developer else None


# ------------------------------------------------------------------- listings

@router.post("/listings")
async def publish_listing(
    body: ListingCreateIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    developer_id = await _developer_id(db, user)
    if developer_id is None:
        raise HTTPException(status_code=404, detail="developer not registered")
    try:
        row = await extension_marketplace_service.publish_listing(
            db,
            developer_id=developer_id,
            application_id=body.application_id,
            name=body.name,
            description=body.description,
            category=body.category,
            price=body.price,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    if row is None:
        raise HTTPException(status_code=404, detail="application not found")
    await db.commit()
    return row


@router.get("/listings")
async def list_listings(
    category: Optional[str] = None,
    limit: int = Query(default=100, ge=1, le=200),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("marketplace:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    rows = await extension_marketplace_service.list_listings(
        db, category=category, published=True, limit=limit
    )
    return {"total": len(rows), "listings": rows}


@router.get("/listings/{item_id}")
async def get_listing(
    item_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("marketplace:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    row = await extension_marketplace_service.get_listing(db, item_id)
    if row is None:
        raise HTTPException(status_code=404, detail="listing not found")
    return row


@router.post("/listings/{item_id}/verify")
async def verify_listing(
    item_id: str,
    verified: bool = True,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("developers:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    row = await extension_marketplace_service.set_verified(db, item_id, verified=verified)
    if row is None:
        raise HTTPException(status_code=404, detail="listing not found")
    await db.commit()
    return row


# ------------------------------------------------------------------- installs

@router.post("/install")
async def install_extension(
    body: InstallIn,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("marketplace:install")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    try:
        row = await extension_marketplace_service.install(
            db,
            organization_id=org.id,
            item_id=body.item_id,
            installed_by=user.id,
            as_agent=body.as_agent,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    await db.commit()
    return row


@router.get("/installed")
async def installed_extensions(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("marketplace:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    rows = await extension_marketplace_service.installed(db, org.id)
    return {"total": len(rows), "installed": rows}


@router.post("/uninstall")
async def uninstall_extension(
    body: InstallIn,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("marketplace:install")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    row = await extension_marketplace_service.uninstall(db, org.id, body.item_id)
    if row is None:
        raise HTTPException(status_code=404, detail="install not found")
    await db.commit()
    return row


# -------------------------------------------------------------------- reviews

@router.post("/reviews")
async def add_review(
    body: ReviewIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    try:
        row = await extension_marketplace_service.review(
            db,
            item_id=body.item_id,
            user_id=user.id,
            rating=body.rating,
            comment=body.comment,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    await db.commit()
    return row


@router.get("/listings/{item_id}/reviews")
async def listing_reviews(
    item_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("marketplace:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    rows = await extension_marketplace_service.reviews(db, item_id)
    return {"total": len(rows), "reviews": rows}


# --------------------------------------------------------------------- themes

@theme_router.get("")
async def list_themes(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("theme:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    rows = await theme_service.list(db, org.id)
    return {"total": len(rows), "themes": rows}


@theme_router.post("")
async def create_theme(
    body: ThemeCreateIn,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("theme:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    row = await theme_service.create(
        db,
        organization_id=org.id,
        name=body.name,
        config=body.config,
        source=body.source,
        activate=body.activate,
    )
    await db.commit()
    return row


@theme_router.patch("/{theme_id}")
async def update_theme(
    theme_id: str,
    body: ThemeUpdateIn,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("theme:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    row = await theme_service.update(db, org.id, theme_id, config=body.config, name=body.name)
    if row is None:
        raise HTTPException(status_code=404, detail="theme not found")
    await db.commit()
    return row


@theme_router.post("/{theme_id}/activate")
async def activate_theme(
    theme_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("theme:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    row = await theme_service.activate(db, org.id, theme_id)
    if row is None:
        raise HTTPException(status_code=404, detail="theme not found")
    await db.commit()
    return row


@theme_router.delete("/{theme_id}")
async def delete_theme(
    theme_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("theme:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    deleted = await theme_service.delete(db, org.id, theme_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="theme not found")
    await db.commit()
    return {"status": "deleted", "theme_id": theme_id}

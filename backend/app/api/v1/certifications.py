"""Certifications API (Phase 10.7 — Certifications & Credentials).

Certification catalog, attempts (start/complete), automatic credential
issuance with verification metadata, expiry management and recommendations.
"""

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_organization, get_current_user, require_permission
from app.db.database import get_db
from app.learning.certification_service import certification_service
from app.models.employee import Employee
from app.models.organization import Organization
from app.models.user import User

router = APIRouter(prefix="/learning/certifications", tags=["Learning"])


async def _employee_id(db: AsyncSession, org: Organization, user: User) -> str:
    employee = (
        await db.execute(
            select(Employee).where(
                Employee.organization_id == org.id, Employee.user_id == str(user.id)
            )
        )
    ).scalar_one_or_none()
    if employee is None:
        raise HTTPException(status_code=404, detail="Employee profile not found")
    return employee.id


def _certification_payload(cert) -> dict[str, Any]:
    return {
        "id": cert.id,
        "name": cert.name,
        "issuer": cert.issuer,
        "category": cert.category,
        "description": cert.description,
        "skills": cert.skills or [],
        "cost": None,
        "validity_years": cert.validity_years,
        "url": None,
        "status": cert.status,
    }


@router.get("")
async def list_certifications(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("learning:read")),
    db: AsyncSession = Depends(get_db),
    category: Optional[str] = Query(None),
    status: str = Query("published"),
    limit: int = Query(50, ge=1, le=200),
):
    certs = await certification_service.list_certifications(
        db, organization_id=org.id, category=category, status=status, limit=limit
    )
    return [_certification_payload(c) for c in certs]


@router.post("", status_code=201)
async def create_certification(
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("learning:manage")),
    db: AsyncSession = Depends(get_db),
):
    cert = await certification_service.create(db, organization_id=org.id, data=payload)
    await db.commit()
    return _certification_payload(cert)


@router.get("/categories", response_model=list[str])
async def categories(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("learning:read")),
    db: AsyncSession = Depends(get_db),
):
    return await certification_service.categories(db, organization_id=org.id)


@router.get("/my/earned")
async def my_certifications(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("learning:read")),
    db: AsyncSession = Depends(get_db),
    status: Optional[str] = Query(None),
):
    employee_id = await _employee_id(db, org, user)
    return await certification_service.my_certifications(
        db, organization_id=org.id, employee_id=employee_id, status=status
    )


@router.get("/my/recommended")
async def recommended(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("learning:read")),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(5, ge=1, le=20),
):
    employee_id = await _employee_id(db, org, user)
    return await certification_service.recommended_for(
        db, organization_id=org.id, employee_id=employee_id, limit=limit
    )


@router.get("/expiring")
async def expiring(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("learning:manage")),
    db: AsyncSession = Depends(get_db),
    days: int = Query(30, ge=1, le=365),
):
    earned = await certification_service.expiring(db, organization_id=org.id, days=days)
    return [
        {
            "id": row.id,
            "certification_id": row.certification_id,
            "employee_id": row.employee_id,
            "issued_at": row.issued_at.isoformat() if row.issued_at else None,
            "expires_at": row.expires_at.isoformat() if row.expires_at else None,
        }
        for row in earned
    ]


@router.post("/expired/mark")
async def mark_expired(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("learning:manage")),
    db: AsyncSession = Depends(get_db),
):
    count = await certification_service.mark_expired(db, organization_id=org.id)
    await db.commit()
    return {"expired": count}


@router.get("/{certification_id}")
async def certification_detail(
    certification_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("learning:read")),
    db: AsyncSession = Depends(get_db),
):
    cert = await certification_service.get(db, organization_id=org.id, certification_id=certification_id)
    if cert is None:
        raise HTTPException(status_code=404, detail="Certification not found")
    return _certification_payload(cert)


@router.patch("/{certification_id}")
async def update_certification(
    certification_id: str,
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("learning:manage")),
    db: AsyncSession = Depends(get_db),
):
    cert = await certification_service.update(
        db, organization_id=org.id, certification_id=certification_id, data=payload
    )
    if cert is None:
        raise HTTPException(status_code=404, detail="Certification not found")
    await db.commit()
    return _certification_payload(cert)


@router.post("/{certification_id}/attempts", status_code=201)
async def start_attempt(
    certification_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    employee_id = await _employee_id(db, org, user)
    attempt = await certification_service.start_attempt(
        db, organization_id=org.id, certification_id=certification_id, employee_id=employee_id
    )
    if attempt is None:
        raise HTTPException(status_code=404, detail="Certification not available")
    await db.commit()
    return {
        "id": attempt.id,
        "certification_id": certification_id,
        "status": attempt.status,
        "started_at": attempt.attempted_at.isoformat() if attempt.attempted_at else None,
    }


@router.post("/attempts/{attempt_id}/complete")
async def complete_attempt(
    attempt_id: str,
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    employee_id = await _employee_id(db, org, user)
    result = await certification_service.complete_attempt(
        db, organization_id=org.id, attempt_id=attempt_id,
        employee_id=employee_id, score=float(payload.get("score", 0)),
        passed=payload.get("passed"),
        evidence=payload.get("evidence"),
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Attempt not found")
    await db.commit()
    from app.models.certification import CertificationEarned
    earned = (
        await db.execute(
            select(CertificationEarned).where(
                CertificationEarned.organization_id == org.id,
                CertificationEarned.attempt_id == result.id,
            )
        )
    ).scalar_one_or_none()
    return {
        "id": result.id,
        "status": result.status,
        "score": result.score,
        "passed": result.status == "passed",
        "credential_id": earned.credential_id if earned else None,
    }

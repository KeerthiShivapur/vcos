"""Compliance API (Phase 11.12 — Compliance & Legal)."""

from datetime import date
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_organization, get_current_user, require_permission
from app.db.database import get_db
from app.hr.compliance_service import compliance_service
from app.models.employee import Employee
from app.models.organization import Organization
from app.models.user import User

router = APIRouter(prefix="/compliance", tags=["HR Compliance"])


async def _employee_id(db: AsyncSession, org: Organization, user: User) -> str:
    employee = (
        await db.execute(
            select(Employee).where(Employee.organization_id == org.id, Employee.user_id == str(user.id))
        )
    ).scalar_one_or_none()
    if employee is None:
        raise HTTPException(status_code=404, detail="Employee profile not found")
    return employee.id


# ------------------------------------------------------------------ documents

@router.post("/documents")
async def record_document(
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("hr:manage")),
    db: AsyncSession = Depends(get_db),
):
    record = await compliance_service.record_document(
        db, organization_id=org.id, data=payload, reviewed_by=user.id
    )
    await db.commit()
    return {"id": record.id, "title": record.title, "status": record.status}


@router.post("/documents/{record_id}/renew")
async def renew_document(
    record_id: str,
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("hr:manage")),
    db: AsyncSession = Depends(get_db),
):
    record = await compliance_service.renew_document(
        db, organization_id=org.id, record_id=record_id,
        expires_at=payload.get("expires_at"), reference=payload.get("reference"), reviewed_by=user.id,
    )
    if record is None:
        raise HTTPException(status_code=404, detail="Compliance record not found")
    await db.commit()
    return {"id": record.id, "status": record.status}


@router.get("/documents")
async def list_documents(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("hr:read")),
    db: AsyncSession = Depends(get_db),
    employee_id: Optional[str] = Query(None),
    document_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
):
    documents = await compliance_service.list_documents(
        db, organization_id=org.id, employee_id=employee_id,
        document_type=document_type, status=status,
    )
    await db.commit()  # persists expiry-status refreshes
    return documents

# ------------------------------------------------------------------ training

@router.post("/requirements")
async def create_requirement(
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("hr:manage")),
    db: AsyncSession = Depends(get_db),
):
    requirement = await compliance_service.create_requirement(db, organization_id=org.id, data=payload)
    await db.commit()
    return {"id": requirement.id, "name": requirement.name}


@router.get("/requirements")
async def list_requirements(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("hr:read")),
    db: AsyncSession = Depends(get_db),
):
    requirements = await compliance_service.list_requirements(db, organization_id=org.id)
    return [
        {
            "id": requirement.id,
            "name": requirement.name,
            "category": requirement.category,
            "required_for": requirement.required_for or [],
            "frequency_days": requirement.frequency_days,
            "description": requirement.description,
        }
        for requirement in requirements
    ]


@router.post("/trainings")
async def complete_training(
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("hr:manage")),
    db: AsyncSession = Depends(get_db),
):
    try:
        completion = await compliance_service.complete_training(db, organization_id=org.id, data=payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await db.commit()
    return {"id": completion.id, "requirement_id": completion.requirement_id, "completed_at": completion.completed_at.isoformat() if completion.completed_at else None}


@router.get("/trainings")
async def list_trainings(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("hr:read")),
    db: AsyncSession = Depends(get_db),
    employee_id: Optional[str] = Query(None),
):
    return await compliance_service.list_completions(db, organization_id=org.id, employee_id=employee_id)


# ------------------------------------------------------------------ overview

@router.get("/overview")
async def compliance_overview(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("hr:read")),
    db: AsyncSession = Depends(get_db),
):
    return await compliance_service.overview(db, organization_id=org.id)


@router.get("/my")
async def my_compliance(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("hr:read")),
    db: AsyncSession = Depends(get_db),
):
    employee_id = await _employee_id(db, org, user)
    documents = await compliance_service.list_documents(db, organization_id=org.id, employee_id=employee_id)
    trainings = await compliance_service.list_completions(db, organization_id=org.id, employee_id=employee_id)
    missing = await compliance_service.missing_trainings(db, organization_id=org.id)
    my_missing = [item for item in missing if item["employee_id"] == employee_id]
    return {"documents": documents, "trainings": trainings, "missing_trainings": my_missing}

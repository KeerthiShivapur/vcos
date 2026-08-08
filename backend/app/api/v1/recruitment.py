"""Recruitment API (Phase 11.5 — Recruitment).

Jobs, candidates, interviews and offers with the pipeline funnel, AI-lite
candidate matching and the hire bridge that creates the Employee record.
"""

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_organization, get_current_user, require_permission
from app.db.database import get_db
from app.hr.recruitment_service import recruitment_service
from app.models.organization import Organization
from app.models.user import User

router = APIRouter(prefix="/recruitment", tags=["HR Recruitment"])


# ------------------------------------------------------------------ jobs

@router.post("/jobs")
async def create_job(
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("hr:manage")),
    db: AsyncSession = Depends(get_db),
):
    job = await recruitment_service.create_job(db, organization_id=org.id, data=payload, created_by=user.id)
    await db.commit()
    return {"id": job.id, "title": job.title, "status": job.status}


@router.patch("/jobs/{job_id}")
async def update_job(
    job_id: str,
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("hr:manage")),
    db: AsyncSession = Depends(get_db),
):
    job = await recruitment_service.update_job(db, organization_id=org.id, job_id=job_id, data=payload)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    await db.commit()
    return {"id": job.id, "title": job.title, "status": job.status}


@router.get("/jobs")
async def list_jobs(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("hr:read")),
    db: AsyncSession = Depends(get_db),
    status: Optional[str] = Query(None),
):
    return await recruitment_service.list_jobs(db, organization_id=org.id, status=status)


@router.post("/jobs/{job_id}/close")
async def close_job(
    job_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("hr:manage")),
    db: AsyncSession = Depends(get_db),
):
    job = await recruitment_service.close_job(db, organization_id=org.id, job_id=job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    await db.commit()
    return {"id": job.id, "status": job.status}


# ------------------------------------------------------------------ candidates

@router.post("/candidates")
async def add_candidate(
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("hr:manage")),
    db: AsyncSession = Depends(get_db),
):
    try:
        candidate = await recruitment_service.add_candidate(db, organization_id=org.id, data=payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await db.commit()
    return {
        "id": candidate.id,
        "name": candidate.name,
        "stage": candidate.stage,
        "match_score": candidate.match_score,
    }


@router.patch("/candidates/{candidate_id}")
async def update_candidate(
    candidate_id: str,
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("hr:manage")),
    db: AsyncSession = Depends(get_db),
):
    candidate = await recruitment_service.update_candidate(db, organization_id=org.id, candidate_id=candidate_id, data=payload)
    if candidate is None:
        raise HTTPException(status_code=404, detail="Candidate not found")
    await db.commit()
    return {"id": candidate.id, "stage": candidate.stage, "match_score": candidate.match_score}


@router.get("/candidates")
async def list_candidates(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("hr:read")),
    db: AsyncSession = Depends(get_db),
    job_id: Optional[str] = Query(None),
    stage: Optional[str] = Query(None),
):
    return await recruitment_service.list_candidates(db, organization_id=org.id, job_id=job_id, stage=stage)


# ------------------------------------------------------------------ interviews

@router.post("/interviews")
async def schedule_interview(
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("hr:manage")),
    db: AsyncSession = Depends(get_db),
):
    try:
        interview = await recruitment_service.schedule_interview(db, organization_id=org.id, data=payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await db.commit()
    return {"id": interview.id, "status": interview.status, "scheduled_at": interview.scheduled_at}


@router.post("/interviews/{interview_id}/complete")
async def complete_interview(
    interview_id: str,
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("hr:manage")),
    db: AsyncSession = Depends(get_db),
):
    interview = await recruitment_service.complete_interview(
        db, organization_id=org.id, interview_id=interview_id,
        rating=float(payload.get("rating", 0.0)),
        feedback=payload.get("feedback"),
        recommendation=payload.get("recommendation"),
        summary=payload.get("summary"),
    )
    if interview is None:
        raise HTTPException(status_code=404, detail="Interview not found")
    await db.commit()
    return {"id": interview.id, "status": interview.status, "rating": interview.rating}


@router.get("/interviews")
async def list_interviews(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("hr:read")),
    db: AsyncSession = Depends(get_db),
    job_id: Optional[str] = Query(None),
    candidate_id: Optional[str] = Query(None),
):
    return await recruitment_service.list_interviews(db, organization_id=org.id, job_id=job_id, candidate_id=candidate_id)


# ------------------------------------------------------------------ offers

@router.post("/offers")
async def create_offer(
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("hr:manage")),
    db: AsyncSession = Depends(get_db),
):
    try:
        offer = await recruitment_service.create_offer(db, organization_id=org.id, data=payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await db.commit()
    return {"id": offer.id, "status": offer.status, "candidate_id": offer.candidate_id}


@router.post("/offers/{offer_id}/status")
async def update_offer_status(
    offer_id: str,
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("hr:manage")),
    db: AsyncSession = Depends(get_db),
):
    """Transition an offer; accepted offers create the Employee (hire)."""
    try:
        offer, employee = await recruitment_service.update_offer(
            db, organization_id=org.id, offer_id=offer_id,
            status=payload.get("status", "draft"), notes=payload.get("notes"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if offer is None:
        raise HTTPException(status_code=404, detail="Offer not found")
    await db.commit()
    return {
        "id": offer.id,
        "status": offer.status,
        "hired_employee_id": employee.id if employee else None,
        "hired_employee_name": employee.full_name if employee else None,
    }


@router.get("/offers")
async def list_offers(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("hr:read")),
    db: AsyncSession = Depends(get_db),
    candidate_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
):
    return await recruitment_service.list_offers(db, organization_id=org.id, candidate_id=candidate_id, status=status)


# ------------------------------------------------------------------ stats

@router.get("/stats")
async def recruitment_stats(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("hr:read")),
    db: AsyncSession = Depends(get_db),
):
    return await recruitment_service.stats(db, organization_id=org.id)

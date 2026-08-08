"""Assessments API (Phase 10.5 — Skill Assessments with AI-assisted Evaluation).

Admins create assessments, assign them to employees; employees submit answers;
AI auto-scoring plus peer/manager reviews produce scores that feed the skill graph.
"""

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_organization, get_current_user, require_permission
from app.db.database import get_db
from app.learning.assessment_service import assessment_service
from app.models.assessment import Assessment
from app.models.employee import Employee
from app.models.organization import Organization
from app.models.user import User

router = APIRouter(prefix="/learning/assessments", tags=["Learning"])


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


def _assessment_payload(assessment: Assessment) -> dict[str, Any]:
    return {
        "id": assessment.id,
        "title": assessment.title,
        "description": assessment.description,
        "kind": assessment.kind,
        "category": assessment.kind,
        "difficulty": assessment.difficulty,
        "skills": assessment.skills or [],
        "duration_minutes": assessment.duration_minutes,
        "passing_score": assessment.passing_score,
        "question_count": len(assessment.questions or []),
        "status": assessment.status,
        "linked_certification_id": assessment.certification_id,
    }


@router.get("")
async def list_assessments(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("learning:read")),
    db: AsyncSession = Depends(get_db),
    category: Optional[str] = Query(None),
    status: str = Query("published"),
    limit: int = Query(50, ge=1, le=200),
):
    assessments = await assessment_service.list_assessments(
        db, organization_id=org.id, category=category, status=status, limit=limit
    )
    return [_assessment_payload(a) for a in assessments]


@router.post("", status_code=201)
async def create_assessment(
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("learning:manage")),
    db: AsyncSession = Depends(get_db),
):
    assessment = await assessment_service.create(db, organization_id=org.id, data=payload)
    await db.commit()
    return _assessment_payload(assessment)


@router.get("/my/attempts")
async def my_attempts(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("learning:read")),
    db: AsyncSession = Depends(get_db),
    status: Optional[str] = Query(None),
):
    employee_id = await _employee_id(db, org, user)
    attempts = await assessment_service.my_attempts(
        db, organization_id=org.id, employee_id=employee_id
    )
    if status:
        attempts = [a for a in attempts if a.get("status") == status]
    return attempts


@router.get("/reviews/pending")
async def pending_reviews(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("learning:manage")),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(50, ge=1, le=200),
):
    attempts = await assessment_service.pending_reviews(
        db, organization_id=org.id, limit=limit
    )
    return [
        {
            "id": attempt.id,
            "assessment_id": attempt.assessment_id,
            "employee_id": attempt.employee_id,
            "status": attempt.status,
            "submitted_at": attempt.submitted_at.isoformat() if attempt.submitted_at else None,
        }
        for attempt in attempts
    ]


@router.get("/{assessment_id}")
async def assessment_detail(
    assessment_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("learning:read")),
    db: AsyncSession = Depends(get_db),
):
    assessment = await assessment_service.get(db, organization_id=org.id, assessment_id=assessment_id)
    if assessment is None:
        raise HTTPException(status_code=404, detail="Assessment not found")
    payload = _assessment_payload(assessment)
    payload["questions"] = assessment.questions or []
    return payload


@router.post("/{assessment_id}/assign", status_code=201)
async def assign(
    assessment_id: str,
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("learning:manage")),
    db: AsyncSession = Depends(get_db),
):
    employee_id = payload.get("employee_id") or await _employee_id(db, org, user)
    attempt = await assessment_service.assign(
        db, organization_id=org.id, assessment_id=assessment_id, employee_id=employee_id
    )
    if attempt is None:
        raise HTTPException(status_code=404, detail="Assessment or employee not found")
    await db.commit()
    return {"id": attempt.id, "assessment_id": assessment_id, "status": attempt.status}


@router.post("/attempts/{attempt_id}/submit")
async def submit(
    attempt_id: str,
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    employee_id = await _employee_id(db, org, user)
    attempt = await assessment_service.submit(
        db, organization_id=org.id, attempt_id=attempt_id,
        employee_id=employee_id, answers=payload.get("answers", {}),
    )
    if attempt is None:
        raise HTTPException(status_code=404, detail="Attempt not found")
    await db.commit()
    return {
        "id": attempt.id,
        "status": attempt.status,
        "score": attempt.score,
        "passed": attempt.passed,
        "submitted_at": attempt.submitted_at.isoformat() if attempt.submitted_at else None,
    }


@router.post("/attempts/{attempt_id}/evaluate")
async def evaluate(
    attempt_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("learning:manage")),
    db: AsyncSession = Depends(get_db),
    payload: Optional[dict[str, Any]] = None,
):
    reviewer_id = (payload or {}).get("reviewer_id")
    attempt = await assessment_service.evaluate(
        db, organization_id=org.id, attempt_id=attempt_id,
        reviewer_id=reviewer_id or await _employee_id(db, org, user),
        score=(payload or {}).get("score"),
        feedback=(payload or {}).get("feedback"),
    )
    if attempt is None:
        raise HTTPException(status_code=404, detail="Attempt not found")
    await db.commit()
    return {
        "id": attempt.id,
        "status": attempt.status,
        "score": attempt.score,
        "passed": attempt.passed,
        "finalized_at": attempt.evaluated_at.isoformat() if attempt.evaluated_at else None,
    }

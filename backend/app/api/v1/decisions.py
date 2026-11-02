"""Decisions API — the Decision Registry (Phase 4.3)."""

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_client_ip, get_current_organization, require_permission
from app.db.database import get_db
from app.knowledge.decision_service import decision_service
from app.knowledge.presenters import present
from app.models.organization import Organization
from app.models.user import User
from app.schemas.common import Message
from app.schemas.knowledge import (
    DecisionChoose,
    DecisionCreate,
    DecisionOptionOut,
    DecisionOut,
    DecisionParticipantOut,
    DecisionUpdate,
)
from app.intelligence.company_brain import company_brain

router = APIRouter(prefix="/decisions", tags=["Decisions"])


async def _actor(db: AsyncSession, org: Organization, user: User):
    from app.people.employee_service import employee_service

    return await employee_service.get_by_user(db, organization_id=org.id, user_id=user.id)


@router.get("", response_model=list[DecisionOut])
async def list_decisions(
    status: Optional[str] = None,
    search: Optional[str] = None,
    project_id: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("knowledge:read")),
    db: AsyncSession = Depends(get_db),
):
    rows = await decision_service.list_all(
        db, organization_id=org.id, status=status, search=search, project_id=project_id,
        limit=min(limit, 500), offset=offset,
    )
    return [await present(db, organization_id=org.id, entity=row, kind="decision") for row in rows]


@router.post("", response_model=DecisionOut, status_code=201)
async def create_decision(
    payload: DecisionCreate,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("knowledge:manage")),
    db: AsyncSession = Depends(get_db),
):
    actor = await _actor(db, org, user)
    try:
        entity = await decision_service.create(
            db, organization_id=org.id, payload=payload.model_dump(exclude_unset=True),
            actor=actor, ip_address=get_client_ip(request),
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    await db.commit()
    return await present(db, organization_id=org.id, entity=entity, kind="decision")


@router.get("/{decision_id}", response_model=DecisionOut)
async def get_decision(
    decision_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("knowledge:read")),
    db: AsyncSession = Depends(get_db),
):
    entity = await decision_service.get(db, organization_id=org.id, entity_id=decision_id)
    if entity is None:
        raise HTTPException(404, "Decision not found")
    from app.knowledge import knowledge_base as kb

    await kb.register_view(db, organization_id=org.id, entity_type="decision", entity_id=decision_id, user_id=user.id)
    await db.commit()
    return await present(db, organization_id=org.id, entity=entity, kind="decision")


@router.patch("/{decision_id}", response_model=DecisionOut)
async def update_decision(
    decision_id: str,
    payload: DecisionUpdate,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("knowledge:manage")),
    db: AsyncSession = Depends(get_db),
):
    actor = await _actor(db, org, user)
    try:
        entity = await decision_service.update(
            db, organization_id=org.id, entity_id=decision_id,
            payload=payload.model_dump(exclude_unset=True), actor=actor, ip_address=get_client_ip(request),
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    if entity is None:
        raise HTTPException(404, "Decision not found")
    await db.commit()
    return await present(db, organization_id=org.id, entity=entity, kind="decision")


@router.delete("/{decision_id}", response_model=Message)
async def delete_decision(
    decision_id: str,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("knowledge:manage")),
    db: AsyncSession = Depends(get_db),
):
    actor = await _actor(db, org, user)
    if not await decision_service.delete(
        db, organization_id=org.id, entity_id=decision_id, actor=actor, ip_address=get_client_ip(request)
    ):
        raise HTTPException(404, "Decision not found")
    await db.commit()
    return Message(message="Decision deleted")


@router.get("/{decision_id}/options", response_model=list[DecisionOptionOut])
async def decision_options(
    decision_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("knowledge:read")),
    db: AsyncSession = Depends(get_db),
):
    if await decision_service.get(db, organization_id=org.id, entity_id=decision_id) is None:
        raise HTTPException(404, "Decision not found")
    rows = await decision_service.options(db, organization_id=org.id, decision_id=decision_id)
    return [
        {
            "id": o.id,
            "decision_id": o.decision_id,
            "title": o.title,
            "description": o.description,
            "pros": o.pros,
            "cons": o.cons,
            "chosen": o.chosen,
            "chosen_reason": o.chosen_reason,
            "sort_order": o.sort_order,
        }
        for o in rows
    ]


@router.get("/{decision_id}/participants", response_model=list[DecisionParticipantOut])
async def decision_participants(
    decision_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("knowledge:read")),
    db: AsyncSession = Depends(get_db),
):
    if await decision_service.get(db, organization_id=org.id, entity_id=decision_id) is None:
        raise HTTPException(404, "Decision not found")
    rows = await decision_service.participants(db, organization_id=org.id, decision_id=decision_id)
    from app.knowledge import knowledge_base as kb

    names = await kb.employee_names(db, employee_ids=[p.employee_id for p in rows])
    return [
        {
            "id": p.id,
            "decision_id": p.decision_id,
            "employee_id": p.employee_id,
            "employee_name": names.get(p.employee_id),
            "role": p.role,
        }
        for p in rows
    ]


@router.post("/{decision_id}/choose", response_model=DecisionOut)
async def choose_option(
    decision_id: str,
    payload: DecisionChoose,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("knowledge:manage")),
    db: AsyncSession = Depends(get_db),
):
    actor = await _actor(db, org, user)
    entity = await decision_service.choose(
        db, organization_id=org.id, decision_id=decision_id, option_id=payload.option_id,
        reason=payload.reason, actor=actor, ip_address=get_client_ip(request),
    )
    if entity is None:
        raise HTTPException(404, "Decision or option not found")
    await db.commit()
    return await present(db, organization_id=org.id, entity=entity, kind="decision")


@router.post("/{decision_id}/status", response_model=DecisionOut)
async def transition_decision(
    decision_id: str,
    payload: dict,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("knowledge:manage")),
    db: AsyncSession = Depends(get_db),
):
    actor = await _actor(db, org, user)
    entity = await decision_service.transition(
        db, organization_id=org.id, decision_id=decision_id, status=payload.get("status", ""),
        note=payload.get("note"), actor=actor, ip_address=get_client_ip(request),
    )
    if entity is None:
        raise HTTPException(400, "Invalid decision status transition")
    await db.commit()
    return await present(db, organization_id=org.id, entity=entity, kind="decision")


@router.post("/{decision_id}/actions/{action_index}/execute", response_model=dict)
async def execute_follow_up_action(
    decision_id: str,
    action_index: int,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("knowledge:manage")),
    db: AsyncSession = Depends(get_db),
):
    """Slice 4A — convert a follow-up action into a real task."""
    from app.schemas.work import TaskOut
    from app.api.v1.tasks import _task_payload
    from app.work.task_service import task_service

    actor = await _actor(db, org, user)
    try:
        result = await decision_service.execute_action(
            db, organization_id=org.id, decision_id=decision_id, action_index=action_index,
            actor=actor, ip_address=get_client_ip(request),
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    if result is None:
        raise HTTPException(400, "Action not executable (missing, already executed, or decision not found)")
    decision, task = result
    await db.commit()
    task = await task_service.get(db, organization_id=org.id, task_id=task.id)
    return {
        "decision": await present(db, organization_id=org.id, entity=decision, kind="decision"),
        "task": TaskOut.model_validate(_task_payload(task)),
    }


@router.get("/{decision_id}/tasks", response_model=list[dict])
async def decision_tasks(
    decision_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("knowledge:read")),
    db: AsyncSession = Depends(get_db),
):
    """Every task this decision produced, with execution status."""
    if await decision_service.get(db, organization_id=org.id, entity_id=decision_id) is None:
        raise HTTPException(404, "Decision not found")
    from app.api.v1.tasks import _task_payload

    tasks = await decision_service.tasks_for(db, organization_id=org.id, decision_id=decision_id)
    return [_task_payload(t) for t in tasks]


# ================================================================================
# Phase H — Institutional Learning Integration
# ================================================================================

@router.get("/{decision_id}/learning")
async def decision_learning(
    decision_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("knowledge:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Decision-relevant institutional learning from the Company Brain.

    Returns lessons, precedents, patterns, and contradictions relevant to this decision.
    Enables: "What has the company learned that's relevant to this decision?"
    """
    # Verify decision access
    if await decision_service.get(db, organization_id=org.id, entity_id=decision_id) is None:
        raise HTTPException(404, "Decision not found")

    # Query Company Brain for learning about this decision
    result = await company_brain.answer(
        db, org.id, f"What did we learn about decision {decision_id}?",
        user=user, entity_type="decision", entity_id=decision_id,
    )

    if result is None:
        return {"lessons": [], "patterns": [], "precedents": [], "contradictions": [], "decision_id": decision_id}

    lessons = result.get("lessons", [])
    patterns = result.get("patterns", [])

    # Get company decision precedents
    from app.models.company_operating import CompanyDecisionPrecedent, CompanyDecisionContradiction
    from sqlalchemy import select

    precedent_stmt = select(CompanyDecisionPrecedent).where(
        CompanyDecisionPrecedent.organization_id == org.id,
        CompanyDecisionPrecedent.decision_id == decision_id,
    )
    precedent_result = await db.execute(precedent_stmt)
    precedents = precedent_result.scalars().all()

    # Get contradictions
    contra_stmt = select(CompanyDecisionContradiction).where(
        CompanyDecisionContradiction.organization_id == org.id,
        CompanyDecisionContradiction.decision_id == decision_id,
    )
    contra_result = await db.execute(contra_stmt)
    contradictions = contra_result.scalars().all()

    return {
        "decision_id": decision_id,
        "lessons": lessons,
        "patterns": patterns,
        "precedents": [
            {
                "id": p.id,
                "precedent_decision_id": p.precedent_decision_id,
                "context_signature": p.context_signature,
                "relevance_score": p.relevance_score,
                "evidence_count": p.evidence_count,
                "cited_lesson": p.cited_lesson,
            }
            for p in precedents
        ],
        "contradictions": [
            {
                "id": c.id,
                "contradiction_key": c.contradiction_key,
                "lesson_memory_id": c.lesson_memory_id,
                "precedent_decision_id": c.precedent_decision_id,
                "side_a_json": c.side_a_json,
                "side_b_json": c.side_b_json,
                "status": c.status,
            }
            for c in contradictions
        ],
        "generated_at": result.get("generated_at"),
    }

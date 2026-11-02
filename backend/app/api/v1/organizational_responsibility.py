"""
Phase 4I.9 API — Organizational Responsibility / Accountability endpoints.

These endpoints expose the organizational responsibility engine for:
- Creating and managing responsibilities (RACI)
- Creating accountability links (Commitment → Authorization → Responsibility)
- Querying organizational structure (who is responsible/accountable)
- Detecting organizational integrity issues
- Capacity analysis
"""

from datetime import date, datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_user, get_current_organization, get_current_user_id, get_current_org_id
from app.intelligence.organizational_responsibility_engine import organizational_responsibility_engine
from app.models.execution_strategy import (
    RESPONSIBILITY_TYPES,
    RESPONSIBILITY_SCOPES,
    ACCOUNTABILITY_TYPES,
    RESPONSIBILITY_RACI_ROLES,
)

router = APIRouter(prefix="/organizational-responsibility", tags=["organizational-responsibility"])


# -------------------------------------------------------------------------
# Request/Response Models
# -------------------------------------------------------------------------

class ResponsibilityCreate(BaseModel):
    responsibility_type: str = Field(..., description="Type: accountable|responsible|consulted|informed|delegated|shared|temporary|emergency")
    scope_type: str = Field(..., description="Scope: commitment|objective|initiative|project|department|team|role|person")
    scope_id: Optional[str] = None
    objective_id: Optional[str] = None
    initiative_id: Optional[str] = None
    project_id: Optional[str] = None
    commitment_id: Optional[str] = None
    person_id: Optional[str] = None
    team_id: Optional[str] = None
    department_id: Optional[str] = None
    role_id: Optional[str] = None
    raci_accountable: bool = False
    raci_responsible: bool = True
    raci_consulted: bool = False
    raci_informed: bool = False
    valid_from: Optional[date] = None
    valid_to: Optional[date] = None
    source_event_id: Optional[str] = None
    source_decision_id: Optional[str] = None
    source_commitment_id: Optional[str] = None


class ResponsibilityResponse(BaseModel):
    id: str
    responsibility_type: str
    scope_type: str
    scope_id: Optional[str]
    objective_id: Optional[str]
    initiative_id: Optional[str]
    project_id: Optional[str]
    commitment_id: Optional[str]
    person_id: Optional[str]
    team_id: Optional[str]
    department_id: Optional[str]
    role_id: Optional[str]
    raci_accountable: bool
    raci_responsible: bool
    raci_consulted: bool
    raci_informed: bool
    valid_from: Optional[date]
    valid_to: Optional[date]
    conditions: Optional[list[dict]] = None
    fingerprint: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class AccountabilityLinkCreate(BaseModel):
    commitment_id: str
    authorization_id: str
    responsibility_id: str
    accountability_type: str = Field(..., description="Type: direct|delegated|shared|oversight")
    source_event_id: Optional[str] = None


class AccountabilityLinkResponse(BaseModel):
    id: str
    commitment_id: str
    authorization_id: str
    responsibility_id: str
    accountability_type: str
    fingerprint: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class AssignFromCommitmentRequest(BaseModel):
    commitment_id: str
    assignments: list[dict]


class CapacityAnalysisResponse(BaseModel):
    person_id: str
    person_name: str
    accountable_count: int
    responsible_count: int
    consulted_count: int
    informed_count: int
    total_responsibilities: int
    active_commitments: int
    workload_score: float
    is_overloaded: bool
    commitments: list[dict]


class OrgIntegrityIssue(BaseModel):
    type: str
    details: dict


# -------------------------------------------------------------------------
# Endpoints
# -------------------------------------------------------------------------

@router.post("/responsibilities", response_model=ResponsibilityResponse, status_code=status.HTTP_201_CREATED)
async def create_responsibility(
    data: ResponsibilityCreate,
    db: AsyncSession = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
    user_id: str = Depends(get_current_user_id),
):
    """Create a new organizational responsibility."""
    try:
        responsibility = await organizational_responsibility_engine.create_responsibility(
            db, org_id,
            user_id=user_id,
            responsibility_type=data.responsibility_type,
            scope_type=data.scope_type,
            scope_id=data.scope_id,
            objective_id=data.objective_id,
            initiative_id=data.initiative_id,
            project_id=data.project_id,
            commitment_id=data.commitment_id,
            person_id=data.person_id,
            team_id=data.team_id,
            department_id=data.department_id,
            role_id=data.role_id,
            raci_accountable=data.raci_accountable,
            raci_responsible=data.raci_responsible,
            raci_consulted=data.raci_consulted,
            raci_informed=data.raci_informed,
            valid_from=data.valid_from,
            valid_to=data.valid_to,
            source_event_id=data.source_event_id,
            source_decision_id=data.source_decision_id,
            source_commitment_id=data.source_commitment_id,
        )
        return responsibility
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/responsibilities/{responsibility_id}", response_model=ResponsibilityResponse)
async def get_responsibility(
    responsibility_id: str,
    db: AsyncSession = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
):
    """Get a responsibility by ID."""
    responsibility = await organizational_responsibility_engine.get_responsibility(db, org_id, responsibility_id)
    if not responsibility:
        raise HTTPException(status_code=404, detail="Responsibility not found")
    return responsibility


@router.post("/accountability-links", response_model=AccountabilityLinkResponse, status_code=status.HTTP_201_CREATED)
async def create_accountability_link(
    data: AccountabilityLinkCreate,
    db: AsyncSession = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
    user_id: str = Depends(get_current_user_id),
):
    """Create an accountability link (Commitment → Authorization → Responsibility)."""
    try:
        link = await organizational_responsibility_engine.create_accountability_link(
            db, org_id,
            commitment_id=data.commitment_id,
            authorization_id=data.authorization_id,
            responsibility_id=data.responsibility_id,
            accountability_type=data.accountability_type,
            source_event_id=data.source_event_id,
        )
        return link
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/accountability-links/{link_id}", response_model=AccountabilityLinkResponse)
async def get_accountability_link(
    link_id: str,
    db: AsyncSession = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
):
    """Get an accountability link by ID."""
    link = await organizational_responsibility_engine.get_accountability_link(db, org_id, link_id)
    if not link:
        raise HTTPException(status_code=404, detail="Accountability link not found")
    return link


@router.post("/assign-from-commitment", response_model=list[ResponsibilityResponse])
async def assign_from_commitment(
    data: AssignFromCommitmentRequest,
    db: AsyncSession = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
    user_id: str = Depends(get_current_user_id),
):
    """Assign multiple responsibilities from a commitment authorization."""
    try:
        responsibilities = await organizational_responsibility_engine.assign_responsibilities_from_commitment(
            db, org_id,
            commitment_id=data.commitment_id,
            user_id=user_id,
            assignments=data.assignments,
        )
        return responsibilities
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/commitments/{commitment_id}/responsibilities", response_model=list[ResponsibilityResponse])
async def get_responsibilities_for_commitment(
    commitment_id: str,
    db: AsyncSession = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
):
    """Get all responsibilities for a commitment."""
    responsibilities = await organizational_responsibility_engine.get_responsibilities_for_commitment(
        db, org_id, commitment_id
    )
    return responsibilities


@router.get("/commitments/{commitment_id}/accountability-chain")
async def get_accountability_chain_for_commitment(
    commitment_id: str,
    db: AsyncSession = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
):
    """Get full accountability chain for a commitment (Authorization → Responsibility → Person)."""
    chain = await organizational_responsibility_engine.get_accountability_chain_for_commitment(
        db, org_id, commitment_id
    )
    return chain


@router.get("/people/{person_id}/responsibilities", response_model=list[ResponsibilityResponse])
async def get_responsibilities_for_person(
    person_id: str,
    db: AsyncSession = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
):
    """Get all responsibilities for a person."""
    responsibilities = await organizational_responsibility_engine.get_responsibilities_for_person(
        db, org_id, person_id
    )
    return responsibilities


@router.get("/people/{person_id}/accountability-chain")
async def get_accountability_chain_for_person(
    person_id: str,
    db: AsyncSession = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
):
    """Get all commitments a person is accountable for."""
    chain = await organizational_responsibility_engine.get_accountability_chain_for_person(
        db, org_id, person_id
    )
    return chain


@router.get("/people/{person_id}/capacity", response_model=CapacityAnalysisResponse)
async def analyze_person_capacity(
    person_id: str,
    db: AsyncSession = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
):
    """Analyze capacity/workload for a specific person."""
    analysis = await organizational_responsibility_engine.analyze_person_capacity(
        db, org_id, person_id
    )
    return analysis


@router.get("/integrity/overloaded-people")
async def detect_overloaded_people(
    threshold: int = Query(5, ge=1),
    db: AsyncSession = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
):
    """Detect people with too many accountable responsibilities."""
    overloaded = await organizational_responsibility_engine.detect_overloaded_people(
        db, org_id, threshold
    )
    return {"overloaded_people": overloaded, "threshold": threshold}


@router.get("/integrity/orphaned-responsibilities")
async def detect_orphaned_responsibilities(
    db: AsyncSession = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
):
    """Detect responsibilities not linked to any commitment or objective."""
    orphaned = await organizational_responsibility_engine.detect_orphaned_responsibilities(
        db, org_id
    )
    return {"orphaned_responsibilities": orphaned}


@router.get("/integrity/broken-chains")
async def detect_broken_accountability_chains(
    db: AsyncSession = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
):
    """Detect commitments without full accountability chains."""
    broken = await organizational_responsibility_engine.detect_broken_accountability_chains(
        db, org_id
    )
    return {"broken_chains": broken}


@router.post("/responsibilities/{old_id}/supersede/{new_id}")
async def supersede_responsibility(
    old_id: str,
    new_id: str,
    reason: str = Query(...),
    source_event_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
    user_id: str = Depends(get_current_user_id),
):
    """Supersede a responsibility with a new one (temporal chain)."""
    try:
        old_resp, new_resp = await organizational_responsibility_engine.supersede_responsibility(
            db, org_id, old_id, new_id,
            user_id=user_id, reason=reason, source_event_id=source_event_id
        )
        return {"old_responsibility_id": old_resp.id, "new_responsibility_id": new_resp.id}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# -------------------------------------------------------------------------
# Vocabulary endpoints
# -------------------------------------------------------------------------

@router.get("/vocabulary/responsibility-types")
async def get_responsibility_types():
    """Get canonical responsibility types."""
    return {"types": list(RESPONSIBILITY_TYPES)}

@router.get("/vocabulary/responsibility-scopes")
async def get_responsibility_scopes():
    """Get canonical responsibility scopes."""
    return {"scopes": list(RESPONSIBILITY_SCOPES)}

@router.get("/vocabulary/accountability-types")
async def get_accountability_types():
    """Get canonical accountability types."""
    return {"types": list(ACCOUNTABILITY_TYPES)}

@router.get("/vocabulary/raci-roles")
async def get_raci_roles():
    """Get canonical RACI roles."""
    return {"roles": list(RESPONSIBILITY_RACI_ROLES)}
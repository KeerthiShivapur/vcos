"""
Authorization Engine API Routes.

Provides endpoints for:
- Policy management (Cedar/OPA)
- Authorization decisions
- Entity management
- Policy testing and simulation
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.api.deps import get_current_user, get_db
from app.core.authorization import (
    AuthorizationEngine,
    PolicyEngine,
    PolicyStatus,
    Effect,
    Entity,
    Policy,
    AuthorizationRequest,
    AuthorizationDecision,
    PolicyTestCase,
    PolicyTestResult,
    get_auth_engine,
)
from app.models.user import User
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(tags=["Authorization Engine"])

logger = logging.getLogger(__name__)


# ==================== Models ====================

class EntityCreate(BaseModel):
    entity_type: str
    entity_id: str
    attributes: Dict[str, Any] = {}
    parents: List[str] = []


class EntityResponse(BaseModel):
    id: str
    type: str
    attributes: Dict[str, Any]
    parents: List[str]
    created_at: str
    updated_at: str


class PolicyCreate(BaseModel):
    name: str
    content: str
    engine: str = "cedar"
    description: str = ""
    schema: Optional[Dict[str, Any]] = None
    tags: List[str] = []


class PolicyUpdate(BaseModel):
    content: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    tags: Optional[List[str]] = None


class PolicyResponse(BaseModel):
    id: str
    name: str
    description: str
    engine: str
    content: str
    status: str
    version: int
    schema: Optional[Dict[str, Any]]
    tags: List[str]
    created_by: str
    created_at: str
    updated_at: str
    activated_at: Optional[str] = None


class AuthorizationRequestModel(BaseModel):
    principal_type: str
    principal_id: str
    action: str
    resource_type: str
    resource_id: str
    context: Dict[str, Any] = {}


class AuthorizationResponse(BaseModel):
    allowed: bool
    effect: str
    policies_evaluated: List[str]
    matching_policies: List[str]
    errors: List[str]
    evaluation_time_ms: int
    metadata: Dict[str, Any]


class BatchAuthRequest(BaseModel):
    requests: List[AuthorizationRequestModel]


class PolicyTestCaseModel(BaseModel):
    name: str
    request: AuthorizationRequestModel
    expected: bool
    description: str = ""


class PolicyTestResultModel(BaseModel):
    test_case: PolicyTestCaseModel
    passed: bool
    decision: AuthorizationResponse
    error: Optional[str] = None


class SimulationRequest(BaseModel):
    request: AuthorizationRequestModel
    policy_ids: List[str]


# ==================== Policy Management ====================

@router.post("/authorization/policies", response_model=PolicyResponse)
async def create_policy(
    request: PolicyCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new authorization policy."""
    auth_engine = get_auth_engine()
    
    try:
        engine = PolicyEngine(request.engine)
    except ValueError:
        raise HTTPException(400, f"Invalid policy engine: {request.engine}")
    
    policy = await auth_engine.create_policy(
        name=request.name,
        content=request.content,
        engine=engine,
        description=request.description,
        schema=request.schema,
        tags=request.tags,
        created_by=user.id,
    )
    
    return PolicyResponse(
        id=policy.id,
        name=policy.name,
        description=policy.description,
        engine=policy.engine.value,
        content=policy.content,
        status=policy.status.value,
        version=policy.version,
        schema=policy.schema,
        tags=policy.tags,
        created_by=policy.created_by,
        created_at=policy.created_at.isoformat(),
        updated_at=policy.updated_at.isoformat(),
        activated_at=policy.activated_at.isoformat() if policy.activated_at else None,
    )


@router.get("/authorization/policies", response_model=List[PolicyResponse])
async def list_policies(
    engine: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    tags: Optional[str] = Query(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List authorization policies."""
    auth_engine = get_auth_engine()
    
    engine_enum = PolicyEngine(engine) if engine else None
    status_enum = PolicyStatus(status) if status else None
    tag_list = tags.split(",") if tags else None
    
    policies = await auth_engine.list_policies(engine_enum, status_enum, tag_list)
    
    return [
        PolicyResponse(
            id=p.id,
            name=p.name,
            description=p.description,
            engine=p.engine.value,
            content=p.content,
            status=p.status.value,
            version=p.version,
            schema=p.schema,
            tags=p.tags,
            created_by=p.created_by,
            created_at=p.created_at.isoformat(),
            updated_at=p.updated_at.isoformat(),
            activated_at=p.activated_at.isoformat() if p.activated_at else None,
        )
        for p in policies
    ]


@router.get("/authorization/policies/{policy_id}", response_model=PolicyResponse)
async def get_policy(
    policy_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get policy by ID."""
    auth_engine = get_auth_engine()
    policy = await auth_engine.get_policy(policy_id)
    
    if not policy:
        raise HTTPException(404, "Policy not found")
    
    return PolicyResponse(
        id=policy.id,
        name=policy.name,
        description=policy.description,
        engine=policy.engine.value,
        content=policy.content,
        status=policy.status.value,
        version=policy.version,
        schema=policy.schema,
        tags=policy.tags,
        created_by=policy.created_by,
        created_at=policy.created_at.isoformat(),
        updated_at=policy.updated_at.isoformat(),
        activated_at=policy.activated_at.isoformat() if policy.activated_at else None,
    )


@router.patch("/authorization/policies/{policy_id}", response_model=PolicyResponse)
async def update_policy(
    policy_id: str,
    request: PolicyUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a policy."""
    auth_engine = get_auth_engine()
    
    status_enum = PolicyStatus(request.status) if request.status else None
    
    policy = await auth_engine.update_policy(
        policy_id=policy_id,
        content=request.content,
        description=request.description,
        status=status_enum,
        tags=request.tags,
    )
    
    return PolicyResponse(
        id=policy.id,
        name=policy.name,
        description=policy.description,
        engine=policy.engine.value,
        content=policy.content,
        status=policy.status.value,
        version=policy.version,
        schema=policy.schema,
        tags=policy.tags,
        created_by=policy.created_by,
        created_at=policy.created_at.isoformat(),
        updated_at=policy.updated_at.isoformat(),
        activated_at=policy.activated_at.isoformat() if policy.activated_at else None,
    )


@router.delete("/authorization/policies/{policy_id}")
async def delete_policy(
    policy_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a policy."""
    auth_engine = get_auth_engine()
    success = await auth_engine.delete_policy(policy_id)
    
    if not success:
        raise HTTPException(404, "Policy not found")
    
    return {"success": True}


@router.post("/authorization/policies/{policy_id}/activate", response_model=PolicyResponse)
async def activate_policy(
    policy_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Activate a policy."""
    auth_engine = get_auth_engine()
    policy = await auth_engine.activate_policy(policy_id)
    
    return PolicyResponse(
        id=policy.id,
        name=policy.name,
        description=policy.description,
        engine=policy.engine.value,
        content=policy.content,
        status=policy.status.value,
        version=policy.version,
        schema=policy.schema,
        tags=policy.tags,
        created_by=policy.created_by,
        created_at=policy.created_at.isoformat(),
        updated_at=policy.updated_at.isoformat(),
        activated_at=policy.activated_at.isoformat() if policy.activated_at else None,
    )


@router.post("/authorization/policies/{policy_id}/deactivate", response_model=PolicyResponse)
async def deactivate_policy(
    policy_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Deactivate a policy."""
    auth_engine = get_auth_engine()
    policy = await auth_engine.deactivate_policy(policy_id)
    
    return PolicyResponse(
        id=policy.id,
        name=policy.name,
        description=policy.description,
        engine=policy.engine.value,
        content=policy.content,
        status=policy.status.value,
        version=policy.version,
        schema=policy.schema,
        tags=policy.tags,
        created_by=policy.created_by,
        created_at=policy.created_at.isoformat(),
        updated_at=policy.updated_at.isoformat(),
        activated_at=policy.activated_at.isoformat() if policy.activated_at else None,
    )


@router.get("/authorization/policies/{policy_id}/versions", response_model=List[PolicyResponse])
async def get_policy_versions(
    policy_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get all versions of a policy."""
    auth_engine = get_auth_engine()
    versions = auth_engine.get_policy_versions(policy_id)
    
    return [
        PolicyResponse(
            id=p.id,
            name=p.name,
            description=p.description,
            engine=p.engine.value,
            content=p.content,
            status=p.status.value,
            version=p.version,
            schema=p.schema,
            tags=p.tags,
            created_by=p.created_by,
            created_at=p.created_at.isoformat(),
            updated_at=p.updated_at.isoformat(),
            activated_at=p.activated_at.isoformat() if p.activated_at else None,
        )
        for p in versions
    ]


# ==================== Entity Management ====================

@router.post("/authorization/entities", response_model=EntityResponse)
async def create_entity(
    request: EntityCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create an authorization entity."""
    auth_engine = get_auth_engine()
    
    entity = await auth_engine.create_entity(
        entity_type=request.entity_type,
        entity_id=request.entity_id,
        attributes=request.attributes,
        parents=request.parents,
    )
    
    return EntityResponse(
        id=entity.id,
        type=entity.type,
        attributes=entity.attributes,
        parents=entity.parents,
        created_at=entity.created_at.isoformat(),
        updated_at=entity.updated_at.isoformat(),
    )


@router.get("/authorization/entities/{entity_type}/{entity_id}", response_model=EntityResponse)
async def get_entity(
    entity_type: str,
    entity_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get entity by type and ID."""
    auth_engine = get_auth_engine()
    entity = await auth_engine.get_entity(entity_type, entity_id)
    
    if not entity:
        raise HTTPException(404, "Entity not found")
    
    return EntityResponse(
        id=entity.id,
        type=entity.type,
        attributes=entity.attributes,
        parents=entity.parents,
        created_at=entity.created_at.isoformat(),
        updated_at=entity.updated_at.isoformat(),
    )


@router.patch("/authorization/entities/{entity_type}/{entity_id}", response_model=EntityResponse)
async def update_entity(
    entity_type: str,
    entity_id: str,
    request: EntityCreate,  # Reuse for update
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update an entity."""
    auth_engine = get_auth_engine()
    
    entity = await auth_engine.update_entity(
        entity_type=entity_type,
        entity_id=entity_id,
        attributes=request.attributes,
        parents=request.parents,
    )
    
    return EntityResponse(
        id=entity.id,
        type=entity.type,
        attributes=entity.attributes,
        parents=entity.parents,
        created_at=entity.created_at.isoformat(),
        updated_at=entity.updated_at.isoformat(),
    )


@router.delete("/authorization/entities/{entity_type}/{entity_id}")
async def delete_entity(
    entity_type: str,
    entity_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete an entity."""
    auth_engine = get_auth_engine()
    success = await auth_engine.delete_entity(entity_type, entity_id)
    
    if not success:
        raise HTTPException(404, "Entity not found")
    
    return {"success": True}


# ==================== Authorization ====================

@router.post("/authorization/check", response_model=AuthorizationResponse)
async def check_authorization(
    request: AuthorizationRequestModel,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Check authorization for a request."""
    auth_engine = get_auth_engine()
    
    try:
        decision = await auth_engine.authorize(
            principal_type=request.principal_type,
            principal_id=request.principal_id,
            action=request.action,
            resource_type=request.resource_type,
            resource_id=request.resource_id,
            context=request.context,
        )
    except ValueError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        raise HTTPException(500, f"Authorization error: {e}")
    
    return AuthorizationResponse(
        allowed=decision.allowed,
        effect=decision.effect.value,
        policies_evaluated=decision.policies_evaluated,
        matching_policies=decision.matching_policies,
        errors=decision.errors,
        evaluation_time_ms=decision.evaluation_time_ms,
        metadata=decision.metadata,
    )


@router.post("/authorization/batch-check", response_model=List[AuthorizationResponse])
async def batch_check_authorization(
    request: BatchAuthRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Check authorization for multiple requests."""
    auth_engine = get_auth_engine()
    
    auth_requests = [
        AuthorizationRequest(
            principal=Entity(id=r.principal_id, type=r.principal_type),
            action=r.action,
            resource=Entity(id=r.resource_id, type=r.resource_type),
            context=r.context,
        )
        for r in request.requests
    ]
    
    decisions = await auth_engine.batch_authorize(auth_requests)
    
    return [
        AuthorizationResponse(
            allowed=d.allowed,
            effect=d.effect.value,
            policies_evaluated=d.policies_evaluated,
            matching_policies=d.matching_policies,
            errors=d.errors,
            evaluation_time_ms=d.evaluation_time_ms,
            metadata=d.metadata,
        )
        for d in decisions
    ]


# ==================== Policy Testing ====================

@router.post("/authorization/policies/{policy_id}/test", response_model=List[PolicyTestResultModel])
async def test_policy(
    policy_id: str,
    test_cases: List[PolicyTestCaseModel],
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Test a policy against test cases."""
    auth_engine = get_auth_engine()
    
    test_case_objects = [
        PolicyTestCase(
            name=tc.name,
            request=AuthorizationRequest(
                principal=Entity(id=tc.request.principal_id, type=tc.request.principal_type),
                action=tc.request.action,
                resource=Entity(id=tc.request.resource_id, type=tc.request.resource_type),
                context=tc.request.context,
            ),
            expected=tc.expected,
            description=tc.description,
        )
        for tc in test_cases
    ]
    
    results = await auth_engine.test_policy(policy_id, test_case_objects)
    
    return [
        PolicyTestResultModel(
            test_case=PolicyTestCaseModel(
                name=r.test_case.name,
                request=AuthorizationRequestModel(
                    principal_type=r.test_case.request.principal.type,
                    principal_id=r.test_case.request.principal.id,
                    action=r.test_case.request.action,
                    resource_type=r.test_case.request.resource.type,
                    resource_id=r.test_case.request.resource.id,
                    context=r.test_case.request.context,
                ),
                expected=r.test_case.expected,
                description=r.test_case.description,
            ),
            passed=r.passed,
            decision=AuthorizationResponse(
                allowed=r.decision.allowed,
                effect=r.decision.effect.value,
                policies_evaluated=r.decision.policies_evaluated,
                matching_policies=r.decision.matching_policies,
                errors=r.decision.errors,
                evaluation_time_ms=r.decision.evaluation_time_ms,
                metadata=r.decision.metadata,
            ),
            error=r.error,
        )
        for r in results
    ]


@router.post("/authorization/simulate", response_model=Dict[str, AuthorizationResponse])
async def simulate_authorization(
    request: SimulationRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Simulate authorization against multiple policies."""
    auth_engine = get_auth_engine()
    
    auth_request = AuthorizationRequest(
        principal=Entity(id=request.request.principal_id, type=request.request.principal_type),
        action=request.request.action,
        resource=Entity(id=request.request.resource_id, type=request.request.resource_type),
        context=request.request.context,
    )
    
    policies = []
    for pid in request.policy_ids:
        policy = await auth_engine.get_policy(pid)
        if policy:
            policies.append(policy)
    
    if not policies:
        raise HTTPException(404, "No valid policies found")
    
    results = await auth_engine.simulate(auth_request, policies)
    
    return {
        pid: AuthorizationResponse(
            allowed=dec.allowed,
            effect=dec.effect.value,
            policies_evaluated=dec.policies_evaluated,
            matching_policies=dec.matching_policies,
            errors=dec.errors,
            evaluation_time_ms=dec.evaluation_time_ms,
            metadata=dec.metadata,
        )
        for pid, dec in results.items()
    }


# ==================== Schema ====================

class SchemaValidationRequest(BaseModel):
    schema: Dict[str, Any]


@router.post("/authorization/schema/validate")
async def validate_schema(
    request: SchemaValidationRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Validate Cedar schema."""
    auth_engine = get_auth_engine()
    valid, errors = auth_engine.validate_schema(request.schema)
    
    return {"valid": valid, "errors": errors}
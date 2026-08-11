"""Slice 4C — Governance, RBAC & Enterprise Control Foundation.

The governance kernel: scope tree (ABAC context axis), scoped role
assignments, delegations, approval policies and the effective-permission
evaluation endpoint. The backend is the source of truth; the frontend only
mirrors it.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_client_ip, get_current_organization, get_current_user, require_permission
from app.db.database import get_db
from app.models.enterprise import AccessGrant
from app.models.governance import ApprovalPolicy, GovernanceScope
from app.models.organization import Organization
from app.models.role import UserRole
from app.models.user import User
from app.schemas.common import Message
from app.schemas.governance import (
    AssignmentCreate,
    AssignmentOut,
    DelegationCreate,
    DelegationOut,
    EffectivePermissionsOut,
    PolicyCreate,
    PolicyOut,
    PolicyUpdate,
    ScopeCreate,
    ScopeOut,
    ScopeUpdate,
)
from app.services.audit_service import audit_service
from app.services.event_service import event_service
from app.services.governance_service import GovernanceError, governance_service

router = APIRouter(prefix="/governance", tags=["Governance"])


# ------------------------------------------------------------------ scopes
@router.get("/scopes", response_model=list[ScopeOut])
async def list_scopes(
    user: User = Depends(require_permission("governance:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    return await governance_service.list_scopes(db, organization_id=org.id)


@router.post("/scopes", response_model=ScopeOut, status_code=201)
async def create_scope(
    payload: ScopeCreate,
    request: Request,
    actor: User = Depends(require_permission("governance:manage")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    try:
        scope = await governance_service.create_scope(
            db,
            organization_id=org.id,
            name=payload.name,
            scope_type=payload.scope_type,
            parent_id=payload.parent_id,
            entity_id=payload.entity_id,
        )
    except GovernanceError as exc:
        raise HTTPException(400, str(exc)) from exc
    await audit_service.log(
        db,
        organization_id=org.id,
        action="governance.scope.created",
        actor_id=actor.id,
        actor_email=actor.email,
        resource_type="governance_scope",
        resource_id=scope.id,
        ip_address=get_client_ip(request),
        details={"name": scope.name, "scope_type": scope.scope_type, "parent_id": scope.parent_id},
    )
    await event_service.emit(
        db,
        name="governance.scope.created",
        actor_id=actor.id,
        organization_id=org.id,
        payload={"scope_id": scope.id, "name": scope.name, "scope_type": scope.scope_type},
    )
    await db.commit()
    return ScopeOut.model_validate(scope)


@router.patch("/scopes/{scope_id}", response_model=ScopeOut)
async def update_scope(
    scope_id: str,
    payload: ScopeUpdate,
    request: Request,
    actor: User = Depends(require_permission("governance:manage")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    try:
        scope = await governance_service.update_scope(
            db, organization_id=org.id, scope_id=scope_id, name=payload.name
        )
    except GovernanceError as exc:
        raise HTTPException(404, str(exc)) from exc
    await audit_service.log(
        db,
        organization_id=org.id,
        action="governance.scope.updated",
        actor_id=actor.id,
        actor_email=actor.email,
        resource_type="governance_scope",
        resource_id=scope.id,
        ip_address=get_client_ip(request),
        details={"name": scope.name},
    )
    await event_service.emit(
        db,
        name="governance.scope.updated",
        actor_id=actor.id,
        organization_id=org.id,
        payload={"scope_id": scope.id, "name": scope.name},
    )
    await db.commit()
    return ScopeOut.model_validate(scope)


@router.delete("/scopes/{scope_id}", response_model=Message)
async def delete_scope(
    scope_id: str,
    request: Request,
    actor: User = Depends(require_permission("governance:manage")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    scope = await governance_service.get_scope(db, organization_id=org.id, scope_id=scope_id)
    if scope is None:
        raise HTTPException(404, "Scope not found")
    try:
        await governance_service.delete_scope(db, organization_id=org.id, scope_id=scope_id)
    except GovernanceError as exc:
        raise HTTPException(400, str(exc)) from exc
    await audit_service.log(
        db,
        organization_id=org.id,
        action="governance.scope.deleted",
        actor_id=actor.id,
        actor_email=actor.email,
        resource_type="governance_scope",
        resource_id=scope_id,
        ip_address=get_client_ip(request),
        details={"name": scope.name},
    )
    await event_service.emit(
        db,
        name="governance.scope.deleted",
        actor_id=actor.id,
        organization_id=org.id,
        payload={"scope_id": scope_id},
    )
    await db.commit()
    return Message(message="Scope deleted")


# ------------------------------------------------- scoped role assignments
@router.get("/assignments", response_model=list[AssignmentOut])
async def list_assignments(
    user_id: Optional[str] = None,
    scope_id: Optional[str] = None,
    role_id: Optional[str] = None,
    user: User = Depends(require_permission("governance:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    return await governance_service.list_assignments(
        db, organization_id=org.id, user_id=user_id, scope_id=scope_id, role_id=role_id
    )


@router.post("/assignments", response_model=AssignmentOut, status_code=201)
async def create_assignment(
    payload: AssignmentCreate,
    request: Request,
    actor: User = Depends(require_permission("governance:manage")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    try:
        assignment = await governance_service.assign_role_at_scope(
            db,
            organization_id=org.id,
            actor_user_id=actor.id,
            user_id=payload.user_id,
            role_id=payload.role_id,
            scope_id=payload.scope_id,
        )
    except GovernanceError as exc:
        raise HTTPException(403, str(exc)) from exc
    await audit_service.log(
        db,
        organization_id=org.id,
        action="governance.assignment.created",
        actor_id=actor.id,
        actor_email=actor.email,
        resource_type="role_assignment",
        resource_id=assignment.id,
        ip_address=get_client_ip(request),
        details={"user_id": payload.user_id, "role_id": payload.role_id, "scope_id": payload.scope_id},
    )
    await event_service.emit(
        db,
        name="governance.assignment.created",
        actor_id=actor.id,
        organization_id=org.id,
        payload={
            "assignment_id": assignment.id,
            "user_id": payload.user_id,
            "role_id": payload.role_id,
            "scope_id": payload.scope_id,
        },
    )
    await db.commit()
    return AssignmentOut.model_validate(assignment)


@router.delete("/assignments/{assignment_id}", response_model=Message)
async def remove_assignment(
    assignment_id: str,
    request: Request,
    actor: User = Depends(require_permission("governance:manage")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    assignment = await db.get(UserRole, assignment_id)
    if assignment is None or assignment.organization_id != org.id:
        raise HTTPException(404, "Assignment not found")
    await audit_service.log(
        db,
        organization_id=org.id,
        action="governance.assignment.removed",
        actor_id=actor.id,
        actor_email=actor.email,
        resource_type="role_assignment",
        resource_id=assignment_id,
        ip_address=get_client_ip(request),
        details={"user_id": assignment.user_id, "role_id": assignment.role_id, "scope_id": assignment.scope_id},
    )
    await event_service.emit(
        db,
        name="governance.assignment.removed",
        actor_id=actor.id,
        organization_id=org.id,
        payload={
            "assignment_id": assignment_id,
            "user_id": assignment.user_id,
            "role_id": assignment.role_id,
            "scope_id": assignment.scope_id,
        },
    )
    await governance_service.remove_assignment(db, organization_id=org.id, assignment_id=assignment_id)
    await db.commit()
    return Message(message="Assignment removed")


# ------------------------------------------------------------- delegations
@router.get("/delegations", response_model=list[DelegationOut])
async def list_delegations(
    granted_to: Optional[str] = None,
    granted_by: Optional[str] = None,
    status: Optional[str] = None,
    user: User = Depends(require_permission("governance:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    return await governance_service.list_delegations(
        db, organization_id=org.id, granted_to=granted_to, granted_by=granted_by, status=status
    )


@router.post("/delegations", response_model=DelegationOut, status_code=201)
async def create_delegation(
    payload: DelegationCreate,
    request: Request,
    actor: User = Depends(require_permission("governance:manage")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    try:
        grant = await governance_service.create_delegation(
            db,
            organization_id=org.id,
            actor_user_id=actor.id,
            granted_to_user=payload.granted_to_user,
            permission_code=payload.permission_code,
            scope_id=payload.scope_id,
            reason=payload.reason,
            starts_at=payload.starts_at,
            expires_at=payload.expires_at,
        )
    except GovernanceError as exc:
        raise HTTPException(403, str(exc)) from exc
    await audit_service.log(
        db,
        organization_id=org.id,
        action="governance.delegation.created",
        actor_id=actor.id,
        actor_email=actor.email,
        resource_type="delegation",
        resource_id=grant.id,
        ip_address=get_client_ip(request),
        details={
            "granted_to_user": payload.granted_to_user,
            "permission_code": payload.permission_code,
            "scope_id": payload.scope_id,
            "expires_at": payload.expires_at.isoformat() if payload.expires_at else None,
            "reason": payload.reason,
        },
    )
    await event_service.emit(
        db,
        name="governance.delegation.created",
        actor_id=actor.id,
        organization_id=org.id,
        payload={
            "grant_id": grant.id,
            "granted_to_user": payload.granted_to_user,
            "permission_code": payload.permission_code,
            "scope_id": payload.scope_id,
            "expires_at": payload.expires_at.isoformat() if payload.expires_at else None,
        },
    )
    # Targeted, bounded notification to the delegate only.
    from app.models.employee import Employee
    from app.services.work_alerts import notify_employee

    delegate_employee = (
        await db.execute(
            select(Employee).where(
                Employee.organization_id == org.id, Employee.user_id == payload.granted_to_user
            ).limit(1)
        )
    ).scalar_one_or_none()
    if delegate_employee is not None:
        await notify_employee(
            db,
            organization_id=org.id,
            employee_id=delegate_employee.id,
            type="governance.delegation",
            title=f"Authority delegated to you: {payload.permission_code}",
            body=payload.reason or "Temporary access granted",
            actor_id=actor.id,
            priority="high",
            entity_type="delegation",
            entity_id=grant.id,
            link="/governance?tab=delegations",
        )
    await db.commit()
    return DelegationOut.model_validate(grant)


@router.post("/delegations/{grant_id}/revoke", response_model=DelegationOut)
async def revoke_delegation(
    grant_id: str,
    request: Request,
    actor: User = Depends(require_permission("governance:manage")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    try:
        grant = await governance_service.revoke_delegation(
            db, organization_id=org.id, grant_id=grant_id, actor_user_id=actor.id
        )
    except GovernanceError as exc:
        raise HTTPException(403, str(exc)) from exc
    await audit_service.log(
        db,
        organization_id=org.id,
        action="governance.delegation.revoked",
        actor_id=actor.id,
        actor_email=actor.email,
        resource_type="delegation",
        resource_id=grant.id,
        ip_address=get_client_ip(request),
        details={"granted_to_user": grant.granted_to_user, "permission_code": grant.permission_code},
    )
    await event_service.emit(
        db,
        name="governance.delegation.revoked",
        actor_id=actor.id,
        organization_id=org.id,
        payload={"grant_id": grant.id, "granted_to_user": grant.granted_to_user},
    )
    await db.commit()
    return DelegationOut.model_validate(grant)


# ------------------------------------------------- effective permissions
@router.get("/effective-permissions", response_model=EffectivePermissionsOut)
async def effective_permissions(
    user_id: str,
    scope_id: Optional[str] = None,
    permission: Optional[str] = Query(default=None, max_length=120),
    user: User = Depends(require_permission("governance:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    target = await db.get(User, user_id)
    if target is None or target.organization_id != org.id:
        raise HTTPException(404, "User not found")
    if scope_id:
        scope = await governance_service.get_scope(db, organization_id=org.id, scope_id=scope_id)
        if scope is None:
            raise HTTPException(404, "Scope not found")
    codes = await governance_service.effective_permission_codes(
        db, organization_id=org.id, user_id=user_id, scope_id=scope_id
    )
    return EffectivePermissionsOut(
        user_id=user_id,
        scope_id=scope_id,
        permissions=sorted(codes),
        has_permission={permission: permission in codes} if permission else {},
    )


# ------------------------------------------------------- approval policies
@router.get("/policies", response_model=list[PolicyOut])
async def list_policies(
    user: User = Depends(require_permission("governance:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    return await governance_service.list_policies(db, organization_id=org.id)


@router.post("/policies", response_model=PolicyOut, status_code=201)
async def create_policy(
    payload: PolicyCreate,
    request: Request,
    actor: User = Depends(require_permission("governance:manage")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    try:
        policy = await governance_service.create_policy(
            db,
            organization_id=org.id,
            name=payload.name,
            approval_type=payload.approval_type,
            required_permission=payload.required_permission,
            scope_id=payload.scope_id,
            self_approval_allowed=payload.self_approval_allowed,
            description=payload.description,
        )
    except GovernanceError as exc:
        raise HTTPException(400, str(exc)) from exc
    await audit_service.log(
        db,
        organization_id=org.id,
        action="governance.policy.created",
        actor_id=actor.id,
        actor_email=actor.email,
        resource_type="approval_policy",
        resource_id=policy.id,
        ip_address=get_client_ip(request),
        details={"name": policy.name, "required_permission": policy.required_permission},
    )
    await event_service.emit(
        db,
        name="governance.policy.created",
        actor_id=actor.id,
        organization_id=org.id,
        payload={"policy_id": policy.id, "name": policy.name},
    )
    await db.commit()
    return PolicyOut.model_validate(policy)


@router.patch("/policies/{policy_id}", response_model=PolicyOut)
async def update_policy(
    policy_id: str,
    payload: PolicyUpdate,
    request: Request,
    actor: User = Depends(require_permission("governance:manage")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    data = payload.model_dump(exclude_unset=True)
    try:
        policy = await governance_service.update_policy(
            db, organization_id=org.id, policy_id=policy_id, **data
        )
    except GovernanceError as exc:
        raise HTTPException(404 if "not found" in str(exc) else 400, str(exc)) from exc
    await audit_service.log(
        db,
        organization_id=org.id,
        action="governance.policy.updated",
        actor_id=actor.id,
        actor_email=actor.email,
        resource_type="approval_policy",
        resource_id=policy.id,
        ip_address=get_client_ip(request),
        details={"name": policy.name},
    )
    await event_service.emit(
        db,
        name="governance.policy.updated",
        actor_id=actor.id,
        organization_id=org.id,
        payload={"policy_id": policy.id, "name": policy.name},
    )
    await db.commit()
    return PolicyOut.model_validate(policy)

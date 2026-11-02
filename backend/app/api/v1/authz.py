from fastapi import APIRouter, Depends, HTTPException, status, Query, Body
from pydantic import BaseModel, Field
from typing import Dict, List, Optional, Any
from datetime import datetime
from typing import Set

from app.core.abac import (
    policy_engine, role_manager, scim_manager, fido2_manager,
    Policy, RoleManager, SCIMManager, FIDO2Manager,
    Subject, Resource, ResourceType, Action, Environment, PolicyEngine, Condition,
    SCIMManager, FIDO2Manager
)
from app.api.deps import get_current_user, get_current_organization
from app.models.organization import Organization
from app.models.user import User


router = APIRouter(prefix="/authz", tags=["authorization"])


class PolicyCreate(BaseModel):
    name: str
    description: str
    effect: str
    actions: List[str]
    resources: List[str]
    conditions: List[Dict] = []
    priority: int = 0


class PolicyResponse(BaseModel):
    id: str
    name: str
    description: str
    effect: str
    actions: List[str]
    resources: List[str]
    conditions: List[Dict]
    priority: int
    created_at: datetime
    updated_at: datetime
    created_by: Optional[str]
    is_active: bool


class RoleAssignment(BaseModel):
    user_id: str
    role: str
    resource_id: Optional[str] = None


class RoleResponse(BaseModel):
    user_id: str
    role: str
    resource_id: Optional[str]
    assigned_at: datetime


class PermissionCheck(BaseModel):
    user_id: str
    action: str
    resource_type: str
    resource_id: str
    context: Optional[Dict] = {}


class PermissionResponse(BaseModel):
    allowed: bool
    reason: Optional[str] = None


class SCIMUserCreate(BaseModel):
    userName: str
    name: Dict[str, str]
    displayName: Optional[str] = None
    emails: List[Dict[str, str]] = []
    phoneNumbers: List[Dict[str, str]] = []
    active: bool = True
    externalId: Optional[str] = None
    roles: List[Dict] = []


class SCIMUserUpdate(BaseModel):
    userName: Optional[str] = None
    name: Optional[Dict[str, str]] = None
    displayName: Optional[str] = None
    emails: Optional[List[Dict[str, str]]] = None
    phoneNumbers: Optional[List[Dict[str, str]]] = None
    active: Optional[bool] = None
    roles: Optional[List[Dict]] = None


class FIDO2RegistrationStart(BaseModel):
    user_id: str
    user_name: str
    user_display_name: str


class FIDO2RegistrationComplete(BaseModel):
    user_id: str
    attestation_object: str
    client_data_json: str


class FIDO2AuthStart(BaseModel):
    user_id: str


class FIDO2AuthComplete(BaseModel):
    user_id: str
    credential_id: str
    authenticator_data: str
    client_data_json: str
    signature: str


class AccessEvaluationRequest(BaseModel):
    user_id: str
    action: str
    resource_type: str
    resource_id: str
    context: Optional[Dict] = {}


@router.post("/policies", response_model=PolicyResponse, status_code=status.HTTP_201_CREATED)
async def create_policy(
    policy: PolicyCreate,
    current_user: User = Depends(get_current_user),
):
    policy = Policy(
        id=f"policy-{datetime.utcnow().timestamp()}",
        name=policy.name,
        description=policy.description,
        effect=policy.effect,
        actions=[Action(a) for a in policy.actions],
        resources=[ResourceType(r) for r in policy.resources],
        conditions=[
            Condition(c["attribute"], c["operator"], c["value"])
            for c in policy.conditions
        ],
        priority=policy.priority,
        created_by=current_user.id,
    )
    policy_engine.add_policy(policy)
    
    return PolicyResponse(
        id=policy.id,
        name=policy.name,
        description=policy.description,
        effect=policy.effect,
        actions=policy.actions,
        resources=policy.resources,
        conditions=policy.conditions,
        priority=policy.priority,
        created_at=policy.created_at,
        updated_at=policy.updated_at,
        created_by=policy.created_by,
        is_active=policy.is_active,
    )


@router.get("/policies", response_model=List[PolicyResponse])
async def list_policies(
    current_user: User = Depends(get_current_user),
):
    policies = policy_engine.list_policies()
    return [
        PolicyResponse(
            id=p.id,
            name=p.name,
            description=p.description,
            effect=p.effect,
            actions=[a.value for a in p.actions],
            resources=[r.value for r in p.resources],
            conditions=[
                {"attribute": c.attribute, "operator": c.operator, "value": c.value}
                for c in p.conditions
            ],
            priority=p.priority,
            created_at=p.created_at,
            updated_at=p.updated_at,
            created_by=p.created_by,
            is_active=p.is_active,
        )
        for p in policies
    ]


@router.get("/policies/{policy_id}", response_model=PolicyResponse)
async def get_policy(
    policy_id: str,
    current_user: User = Depends(get_current_user),
):
    policy = policy_engine.get_policy(policy_id)
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    
    return PolicyResponse(
        id=policy.id,
        name=policy.name,
        description=policy.description,
        effect=policy.effect,
        actions=[a.value for a in policy.actions],
        resources=[r.value for r in policy.resources],
        conditions=[
            {"attribute": c.attribute, "operator": c.operator, "value": c.value}
            for c in policy.conditions
        ],
        priority=policy.priority,
        created_at=policy.created_at,
        updated_at=policy.updated_at,
        created_by=policy.created_by,
        is_active=policy.is_active,
    )


@router.delete("/policies/{policy_id}")
async def delete_policy(
    policy_id: str,
    current_user: User = Depends(get_current_user),
):
    policy_engine.remove_policy(policy_id)
    return {"success": True}


@router.post("/roles", response_model=RoleResponse, status_code=status.HTTP_201_CREATED)
async def assign_role(
    assignment: RoleAssignment,
    current_user: User = Depends(get_current_user),
):
    role_manager.assign_role(assignment.user_id, assignment.role, assignment.resource_id)
    return RoleResponse(
        user_id=assignment.user_id,
        role=assignment.role,
        resource_id=assignment.resource_id,
        assigned_at=datetime.utcnow(),
    )


@router.delete("/roles")
async def remove_role(
    assignment: RoleAssignment,
    current_user: User = Depends(get_current_user),
):
    role_manager.remove_role(assignment.user_id, assignment.role, assignment.resource_id)
    return {"success": True}


@router.get("/roles/{user_id}", response_model=List[RoleResponse])
async def get_user_roles(
    user_id: str,
    resource_id: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
):
    roles = role_manager.get_user_roles(user_id, resource_id)
    return [
        RoleResponse(
            user_id=user_id,
            role=role,
            resource_id=resource_id,
            assigned_at=datetime.utcnow(),
        )
        for role in roles
    ]


@router.post("/check", response_model=PermissionResponse)
async def check_permission(
    check: PermissionCheck,
    current_user: User = Depends(get_current_user),
):
    subject = Subject(
        id=check.user_id,
        type="user",
        attributes={
            "id": Attribute("id", check.user_id),
            "role": Attribute("role", check.context.get("role", "member")),
            "organization_id": Attribute("organization_id", check.context.get("organization_id")),
            "status": Attribute("status", check.context.get("status", "active")),
        }
    )
    
    resource = Resource(
        id=check.resource_id,
        type=ResourceType(check.resource_type),
        attributes={
            "id": Attribute("id", check.resource_id),
            "organization_id": Attribute("organization_id", check.context.get("organization_id")),
            "owner_id": Attribute("owner_id", check.context.get("owner_id")),
        }
    )
    
    environment = Environment(
        current_time=datetime.utcnow(),
        ip_address=check.context.get("ip_address"),
        user_agent=check.context.get("user_agent"),
    )
    
    allowed = policy_engine.evaluate(
        subject,
        Action(check.action),
        resource,
        environment
    )
    
    return PermissionResponse(
        allowed=allowed,
        reason="Policy evaluation result" if allowed else "No matching allow policy or explicit deny"
    )


@router.post("/scim/Users", status_code=status.HTTP_201_CREATED)
async def create_scim_user(
    user: SCIMUserCreate,
    current_user: User = Depends(get_current_user),
):
    return await scim_manager.create_user(user.dict())


@router.get("/scim/Users", response_model=Dict)
async def list_scim_users(
    filter: Optional[str] = Query(None),
    startIndex: int = Query(1, ge=1),
    count: int = Query(100, ge=1, le=1000),
    current_user: User = Depends(get_current_user),
):
    return await scim_manager.list_users(filter, startIndex, count)


@router.get("/scim/Users/{user_id}")
async def get_scim_user(
    user_id: str,
    current_user: User = Depends(get_current_user),
):
    user = await scim_manager.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.patch("/scim/Users/{user_id}")
async def update_scim_user(
    user_id: str,
    user: SCIMUserUpdate,
    current_user: User = Depends(get_current_user),
):
    return await scim_manager.update_user(user_id, user.dict(exclude_unset=True))


@router.delete("/scim/Users/{user_id}")
async def delete_scim_user(
    user_id: str,
    current_user: User = Depends(get_current_user),
):
    await scim_manager.delete_user(user_id)
    return {"success": True}


@router.post("/scim/Groups", status_code=status.HTTP_201_CREATED)
async def create_scim_group(
    group: Dict,
    current_user: User = Depends(get_current_user),
):
    return await scim_manager.create_group(group)


@router.get("/scim/Groups/{group_id}")
async def get_scim_group(
    group_id: str,
    current_user: User = Depends(get_current_user),
):
    group = await scim_manager.get_group(group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    return group


@router.patch("/scim/Groups/{group_id}")
async def update_scim_group(
    group_id: str,
    group: Dict,
    current_user: User = Depends(get_current_user),
):
    return await scim_manager.update_group(group_id, group)


@router.delete("/scim/Groups/{group_id}")
async def delete_scim_group(
    group_id: str,
    current_user: User = Depends(get_current_user),
):
    await scim_manager.delete_group(group_id)
    return {"success": True}


@router.post("/fido2/register/start")
async def fido2_registration_start(
    request: FIDO2RegistrationStart,
    current_user: User = Depends(get_current_user),
):
    options = fido2_manager.generate_registration_challenge(
        request.user_id,
        request.user_name,
        request.user_display_name
    )
    return options


@router.post("/fido2/register/complete")
async def fido2_registration_complete(
    request: FIDO2RegistrationComplete,
    current_user: User = Depends(get_current_user),
):
    credential_id = fido2_manager.verify_registration(
        request.user_id,
        request.attestation_object,
        request.client_data_json
    )
    if not credential_id:
        raise HTTPException(status_code=400, detail="Registration verification failed")
    return {"credential_id": credential_id, "success": True}


@router.post("/fido2/authenticate/start")
async def fido2_authenticate_start(
    request: FIDO2AuthStart,
    current_user: User = Depends(get_current_user),
):
    options = fido2_manager.generate_authentication_challenge(request.user_id)
    if not options:
        raise HTTPException(status_code=400, detail="No credentials registered")
    return options


@router.post("/fido2/authenticate/complete")
async def fido2_authenticate_complete(
    request: FIDO2AuthComplete,
    current_user: User = Depends(get_current_user),
):
    success = fido2_manager.verify_authentication(
        request.user_id,
        request.credential_id,
        request.authenticator_data,
        request.client_data_json,
        request.signature
    )
    if not success:
        raise HTTPException(status_code=401, detail="Authentication failed")
    return {"success": True}


@router.post("/evaluate", response_model=PermissionResponse)
async def evaluate_access(
    request: AccessEvaluationRequest,
    current_user: User = Depends(get_current_user),
):
    subject = Subject(
        id=request.user_id,
        type="user",
        attributes={
            "id": Attribute("id", request.user_id),
            "role": Attribute("role", request.context.get("role", "member")),
            "organization_id": Attribute("organization_id", request.context.get("organization_id")),
            "status": Attribute("status", request.context.get("status", "active")),
        }
    )
    
    resource = Resource(
        id=request.resource_id,
        type=ResourceType(request.resource_type),
        attributes={
            "id": Attribute("id", request.resource_id),
            "organization_id": Attribute("organization_id", request.context.get("organization_id")),
            "owner_id": Attribute("owner_id", request.context.get("owner_id")),
        }
    )
    
    environment = Environment(
        current_time=datetime.utcnow(),
        ip_address=request.context.get("ip_address"),
        user_agent=request.context.get("user_agent"),
    )
    
    allowed = policy_engine.evaluate(
        subject,
        Action(request.action),
        resource,
        environment
    )
    
    return PermissionResponse(
        allowed=allowed,
        reason="Policy evaluation result" if allowed else "No matching allow policy or explicit deny"
    )


@router.get("/policies/engine/status")
async def get_engine_status(
    current_user: User = Depends(get_current_user),
):
    return {
        "total_policies": len(policy_engine.policies),
        "active_policies": len([p for p in policy_engine.policies.values() if p.is_active]),
        "roles_configured": len(role_manager.role_permissions),
        "users_with_roles": len(role_manager.user_roles),
    }
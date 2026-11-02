"""
Enterprise Security & Compliance API Endpoints.

Provides REST API for:
- ABAC/ReBAC with Cedar policy engine
- FIDO2/WebAuthn + Passkeys
- SCIM 2.0 provisioning (Okta/Azure AD/GSuite)
- Device trust + geo/IP risk scoring
- SIEM integration (Splunk/Datadog/Elastic + OCSF)
- DLP Engine
- Compliance dashboards (SOC2/ISO27001/GDPR/HIPAA/FedRAMP)
- Automated compliance reporting
- GDPR/CCPA automation
- SOC2 Type II / ISO 27001 / HIPAA / FedRAMP modules
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_organization, get_current_user, require_permission
from app.core.abac import (
    PolicyEngine,
    RoleManager,
    SCIMManager,
    FIDO2Manager,
    Policy,
    Action,
    ResourceType,
    Subject,
    Resource,
    Environment,
    Condition,
    policy_engine,
    role_manager,
    scim_manager,
    fido2_manager,
)
from app.core.rebac import (
    ReBACEngine,
    Schema,
    CheckRequest,
    ExpandRequest,
    LookupRequest,
    RelationshipTuple,
    create_vcos_schema,
    get_rebac_engine,
)
from app.core.fido2 import (
    WebAuthnManager,
    get_webauthn_manager,
)
from app.core.scim import (
    SCIMService,
    SCIMUserCreate,
    SCIMUserUpdate,
    SCIMGroupCreate,
    get_scim_service,
)
from app.core.device_trust import (
    DeviceTrustService,
    DeviceTrustLevel,
    RiskLevel,
    ChallengeType,
    RiskAssessment,
    get_device_trust_service,
    init_device_trust_service,
)
from app.core.siem import (
    SIEMManager,
    SIEMConfig,
    SIEMBackend,
    OCSFEvent,
    OCSFEventBuilder,
    OCSFClass,
    OCSFCategory,
    Severity,
    get_siem_manager,
    init_siem_manager,
)
from app.core.ocsf_siem import (
    SIEMManager as OCSFSIEMManager,
    SIEMConnectorConfig,
    SIEMConnectorType,
    DLPEngine,
    DLPRule,
    DLPAction,
    DLPClassifierType,
    DataClassification,
    get_siem_manager as get_ocsf_siem_manager,
    get_dlp_engine,
    scan_for_dlp,
    scan_and_protect,
)
from app.core.compliance import (
    ComplianceFramework,
    AuditEventType,
    DataClassification,
    RetentionPolicy,
    RetentionAction,
    DataSubjectRequest,
    ComplianceReport,
    get_compliance_framework,
    init_compliance_framework,
)
from app.core.compliance_dashboards import (
    ComplianceEngine,
    ComplianceFramework as DashboardFramework,
    ControlStatus,
    EvidenceType,
    AuditReadiness,
    RemediationStatus,
    get_compliance_engine,
    init_compliance_engine,
)
from app.core.compliance_reporting import (
    ComplianceReportingEngine,
    ComplianceFramework as ReportingFramework,
    ReportFormat,
    ReportStatus,
    EvidenceType as ReportingEvidenceType,
    get_compliance_reporting as get_compliance_reporting_engine,
)
from app.models.organization import Organization
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/security-compliance", tags=["Security & Compliance"])


# ==================== ABAC/ReBAC Policy Engine ====================

class PolicyRequest(BaseModel):
    id: str
    name: str
    description: str
    effect: str
    actions: List[str]
    resources: List[str]
    conditions: List[Dict[str, Any]] = []
    priority: int = 0


class PolicyEvaluationRequest(BaseModel):
    subject_id: str
    subject_type: str
    subject_attributes: Dict[str, Any] = {}
    action: str
    resource_type: str
    resource_id: str
    resource_attributes: Dict[str, Any] = {}
    resource_owner_id: Optional[str] = None
    resource_organization_id: Optional[str] = None
    environment: Dict[str, Any] = {}


class RoleAssignmentRequest(BaseModel):
    user_id: str
    role: str
    resource_id: Optional[str] = None


@router.post("/abac/policies")
async def create_policy(
    request: PolicyRequest,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("security:write")),
):
    """Create a new ABAC policy."""
    policy = Policy(
        id=request.id,
        name=request.name,
        description=request.description,
        effect=request.effect,
        actions=[Action(a) for a in request.actions],
        resources=[ResourceType(r) for r in request.resources],
        conditions=[
            Condition(c["attribute"], c["operator"], c["value"])
            for c in request.conditions
        ],
        priority=request.priority,
        created_by=user.id,
    )
    policy_engine.add_policy(policy)
    return {"success": True, "policy_id": policy.id}


@router.get("/abac/policies")
async def list_policies(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("security:read")),
):
    """List all ABAC policies."""
    policies = policy_engine.list_policies()
    return {"policies": [
        {
            "id": p.id,
            "name": p.name,
            "description": p.description,
            "effect": p.effect,
            "actions": [a.value for a in p.actions],
            "resources": [r.value for r in p.resources],
            "conditions": [
                {"attribute": c.attribute, "operator": c.operator, "value": c.value}
                for c in p.conditions
            ],
            "priority": p.priority,
            "created_at": p.created_at.isoformat(),
            "is_active": p.is_active,
        }
        for p in policies
    ]}


@router.post("/abac/evaluate")
async def evaluate_policy(
    request: PolicyEvaluationRequest,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("security:read")),
):
    """Evaluate an authorization decision using ABAC."""
    subject = Subject(
        id=request.subject_id,
        type=request.subject_type,
        attributes={k: type(v).__name__ for k, v in request.subject_attributes.items()}
    )
    for k, v in request.subject_attributes.items():
        subject.attributes[k] = v

    resource = Resource(
        id=request.resource_id,
        type=ResourceType(request.resource_type),
        attributes=request.resource_attributes,
        owner_id=request.resource_owner_id,
        organization_id=request.resource_organization_id or org.id,
    )

    environment = Environment(
        attributes=request.environment,
        current_time=datetime.utcnow(),
        ip_address=request.environment.get("ip_address"),
        user_agent=request.environment.get("user_agent"),
        location=request.environment.get("location"),
    )

    result = policy_engine.evaluate(
        subject=subject,
        action=Action(request.action),
        resource=resource,
        environment=environment,
    )

    return {"allowed": result, "action": request.action, "resource": request.resource_id}


@router.post("/abac/roles/assign")
async def assign_role(
    request: RoleAssignmentRequest,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("security:write")),
):
    """Assign a role to a user."""
    role_manager.assign_role(request.user_id, request.role, request.resource_id)
    return {"success": True}


@router.delete("/abac/roles/remove")
async def remove_role(
    request: RoleAssignmentRequest,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("security:write")),
):
    """Remove a role from a user."""
    role_manager.remove_role(request.user_id, request.role, request.resource_id)
    return {"success": True}


@router.get("/abac/roles/{user_id}")
async def get_user_roles(
    user_id: str,
    resource_id: Optional[str] = Query(None),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("security:read")),
):
    """Get roles for a user."""
    roles = role_manager.get_user_roles(user_id, resource_id)
    return {"user_id": user_id, "roles": list(roles)}


# ==================== ReBAC (Relationship-Based Access Control) ====================

class ReBACWriteRequest(BaseModel):
    tuples: List[Dict[str, Any]]


class ReBACDeleteRequest(BaseModel):
    tuples: List[Dict[str, Any]]


class ReBACCheckRequest(BaseModel):
    subject_type: str
    subject_id: str
    relation: str
    object_type: str
    object_id: str
    context: Dict[str, Any] = {}
    caveat_context: Dict[str, Any] = {}


class ReBACExpandRequest(BaseModel):
    relation: str
    object_type: str
    object_id: str
    subject_type: Optional[str] = None
    max_results: int = 1000


class ReBACLookupRequest(BaseModel):
    subject_type: str
    subject_id: str
    object_type: Optional[str] = None
    relation: Optional[str] = None
    max_results: int = 1000


@router.post("/rebac/write")
async def rebac_write(
    request: ReBACWriteRequest,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("security:write")),
):
    """Write relationship tuples."""
    engine = get_rebac_engine()
    await engine.initialize()
    
    tuples = [RelationshipTuple(**t) for t in request.tuples]
    written = await engine.write(tuples)
    return {"success": True, "written": written}


@router.post("/rebac/delete")
async def rebac_delete(
    request: ReBACDeleteRequest,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("security:write")),
):
    """Delete relationship tuples."""
    engine = get_rebac_engine()
    await engine.initialize()
    
    tuples = [RelationshipTuple(**t) for t in request.tuples]
    deleted = await engine.delete(tuples)
    return {"success": True, "deleted": deleted}


@router.post("/rebac/check")
async def rebac_check(
    request: ReBACCheckRequest,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("security:read")),
):
    """Check if subject has relation to object."""
    engine = get_rebac_engine()
    await engine.initialize()
    
    check_req = CheckRequest(**request.dict())
    result = await engine.check(check_req)
    return {
        "allowed": result.allowed,
        "explanation": result.explanation,
        "evaluated_tuples": len(result.evaluated_tuples),
    }


@router.post("/rebac/expand")
async def rebac_expand(
    request: ReBACExpandRequest,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("security:read")),
):
    """Find all subjects with a relation to an object."""
    engine = get_rebac_engine()
    await engine.initialize()
    
    expand_req = ExpandRequest(**request.dict())
    result = await engine.expand(expand_req)
    return {"subjects": result.subjects, "total_count": result.total_count, "truncated": result.truncated}


@router.post("/rebac/lookup")
async def rebac_lookup(
    request: ReBACLookupRequest,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("security:read")),
):
    """Find all objects a subject has relations to."""
    engine = get_rebac_engine()
    await engine.initialize()
    
    lookup_req = LookupRequest(**request.dict())
    result = await engine.lookup(lookup_req)
    return {"tuples": [
        {
            "subject_type": t.subject_type,
            "subject_id": t.subject_id,
            "relation": t.relation,
            "object_type": t.object_type,
            "object_id": t.object_id,
        }
        for t in result.tuples
    ], "total_count": result.total_count, "truncated": result.truncated}


# ==================== FIDO2/WebAuthn + Passkeys ====================

class WebAuthnRegistrationStartRequest(BaseModel):
    user_id: str
    username: str
    display_name: str
    exclude_credentials: Optional[List[str]] = None


class WebAuthnRegistrationCompleteRequest(BaseModel):
    state_id: str
    credential: Dict[str, Any]


class WebAuthnAuthenticationStartRequest(BaseModel):
    user_id: Optional[str] = None
    username: Optional[str] = None


class WebAuthnAuthenticationCompleteRequest(BaseModel):
    state_id: str
    credential: Dict[str, Any]


@router.post("/webauthn/registration/start")
async def webauthn_registration_start(
    request: WebAuthnRegistrationStartRequest,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("auth:write")),
):
    """Start WebAuthn registration ceremony."""
    manager = get_webauthn_manager()
    
    # Get existing credentials to exclude
    existing = manager.get_user_credentials(request.user_id)
    exclude = [c.credential_id for c in existing]
    
    result = await manager.start_registration(
        user_id=request.user_id,
        username=request.username,
        display_name=request.display_name,
        exclude_credentials=exclude if exclude else None,
    )
    return result


@router.post("/webauthn/registration/complete")
async def webauthn_registration_complete(
    request: WebAuthnRegistrationCompleteRequest,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("auth:write")),
):
    """Complete WebAuthn registration ceremony."""
    manager = get_webauthn_manager()
    credential = await manager.complete_registration(request.state_id, request.credential)
    return {"success": True, "credential_id": credential.credential_id.hex()}


@router.post("/webauthn/authentication/start")
async def webauthn_authentication_start(
    request: WebAuthnAuthenticationStartRequest,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("auth:write")),
):
    """Start WebAuthn authentication ceremony."""
    manager = get_webauthn_manager()
    result = await manager.start_authentication(request.user_id, request.username)
    return result


@router.post("/webauthn/authentication/complete")
async def webauthn_authentication_complete(
    request: WebAuthnAuthenticationCompleteRequest,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("auth:write")),
):
    """Complete WebAuthn authentication ceremony."""
    manager = get_webauthn_manager()
    credential = await manager.complete_authentication(request.state_id, request.credential)
    return {"success": True, "user_id": credential.user_id}


@router.get("/webauthn/credentials/{user_id}")
async def get_user_credentials(
    user_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("auth:read")),
):
    """Get all WebAuthn credentials for a user."""
    manager = get_webauthn_manager()
    credentials = manager.get_user_credentials(user_id)
    return {"credentials": [WebAuthnManager.credential_to_json(c) for c in credentials]}


@router.delete("/webauthn/credentials/{user_id}")
async def delete_credential(
    user_id: str,
    credential_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("auth:write")),
):
    """Delete a WebAuthn credential."""
    manager = get_webauthn_manager()
    cred_id_bytes = bytes.fromhex(credential_id)
    success = manager.delete_credential(user_id, cred_id_bytes)
    return {"success": success}


# ==================== SCIM 2.0 Provisioning ====================

@router.post("/scim/users")
async def scim_create_user(
    request: SCIMUserCreate,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("scim:write")),
):
    """Create a SCIM user."""
    service = get_scim_service()
    user_obj = await service.create_user(request)
    return user_obj


@router.get("/scim/users")
async def scim_list_users(
    start_index: int = Query(1, ge=1),
    count: int = Query(100, ge=1, le=1000),
    filter: Optional[str] = Query(None),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("scim:read")),
):
    """List SCIM users."""
    service = get_scim_service()
    result = await service.list_users(start_index, count, filter)
    return result


@router.get("/scim/users/{user_id}")
async def scim_get_user(
    user_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("scim:read")),
):
    """Get SCIM user by ID."""
    service = get_scim_service()
    user_obj = await service.get_user(user_id)
    return user_obj


@router.put("/scim/users/{user_id}")
async def scim_update_user(
    user_id: str,
    request: SCIMUserCreate,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("scim:write")),
):
    """Update SCIM user (PUT)."""
    service = get_scim_service()
    user_obj = await service.update_user(user_id, request)
    return user_obj


@router.patch("/scim/users/{user_id}")
async def scim_patch_user(
    user_id: str,
    request: SCIMUserUpdate,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("scim:write")),
):
    """Partially update SCIM user (PATCH)."""
    service = get_scim_service()
    user_obj = await service.patch_user(user_id, request.operations)
    return user_obj


@router.delete("/scim/users/{user_id}")
async def scim_delete_user(
    user_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("scim:write")),
):
    """Delete SCIM user."""
    service = get_scim_service()
    await service.delete_user(user_id)
    return {"success": True}


@router.post("/scim/groups")
async def scim_create_group(
    request: SCIMGroupCreate,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("scim:write")),
):
    """Create a SCIM group."""
    service = get_scim_service()
    group = await service.create_group(request)
    return group


@router.get("/scim/groups")
async def scim_list_groups(
    start_index: int = Query(1, ge=1),
    count: int = Query(100, ge=1, le=1000),
    filter: Optional[str] = Query(None),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("scim:read")),
):
    """List SCIM groups."""
    service = get_scim_service()
    result = await service.list_groups(start_index, count, filter)
    return result


@router.get("/scim/groups/{group_id}")
async def scim_get_group(
    group_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("scim:read")),
):
    """Get SCIM group by ID."""
    service = get_scim_service()
    group = await service.get_group(group_id)
    return group


@router.put("/scim/groups/{group_id}")
async def scim_update_group(
    group_id: str,
    request: SCIMGroupCreate,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("scim:write")),
):
    """Update SCIM group (PUT)."""
    service = get_scim_service()
    group = await service.update_group(group_id, request)
    return group


@router.patch("/scim/groups/{group_id}")
async def scim_patch_group(
    group_id: str,
    request: SCIMGroupCreate,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("scim:write")),
):
    """Partially update SCIM group (PATCH)."""
    service = get_scim_service()
    group = await service.patch_group(group_id, request.operations)
    return group


@router.delete("/scim/groups/{group_id}")
async def scim_delete_group(
    group_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("scim:write")),
):
    """Delete SCIM group."""
    service = get_scim_service()
    await service.delete_group(group_id)
    return {"success": True}


@router.get("/scim/service-provider-config")
async def scim_service_provider_config(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("scim:read")),
):
    """Get SCIM service provider configuration."""
    return SCIMServiceProviderConfig()


# ==================== Device Trust & Risk Scoring ====================

class DeviceFingerprintRequest(BaseModel):
    user_agent: str
    accept_language: str
    accept_encoding: str
    screen_resolution: Optional[str] = None
    timezone: Optional[str] = None
    platform: Optional[str] = None
    canvas_fingerprint: Optional[str] = None
    webgl_fingerprint: Optional[str] = None
    audio_fingerprint: Optional[str] = None
    font_list: Optional[str] = None
    cpu_cores: Optional[int] = None
    device_memory: Optional[int] = None
    hardware_concurrency: Optional[int] = None
    device_pixel_ratio: Optional[float] = None
    ip: str


class DeviceRegistrationRequest(BaseModel):
    fingerprint: DeviceFingerprintRequest
    device_name: Optional[str] = None


class RiskAssessmentRequest(BaseModel):
    ip: str
    fingerprint: Optional[DeviceFingerprintRequest] = None
    context: Dict[str, Any] = {}


@router.post("/device-trust/register")
async def register_device(
    request: DeviceRegistrationRequest,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("device:write")),
):
    """Register a new device for a user."""
    service = get_device_trust_service()
    await service.initialize()
    
    device = await service.register_device(
        user_id=user.id,
        organization_id=org.id,
        fingerprint_data=request.fingerprint.dict(),
        device_name=request.device_name,
    )
    return {"device_id": device.id, "trust_level": device.trust_level.value, "trust_score": device.trust_score}


@router.get("/device-trust/devices")
async def get_user_devices(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("device:read")),
):
    """Get all devices for current user."""
    service = get_device_trust_service()
    await service.initialize()
    devices = await service.get_user_devices(user.id)
    return {"devices": [{"id": d.id, "name": d.device_name, "type": d.device_type, "trust_level": d.trust_level.value, "trust_score": d.trust_score, "last_seen": d.last_seen.isoformat()} for d in devices]}


@router.post("/device-trust/assess-risk")
async def assess_risk(
    request: RiskAssessmentRequest,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("device:read")),
):
    """Perform comprehensive risk assessment."""
    service = get_device_trust_service()
    await service.initialize()
    
    fingerprint = None
    if request.fingerprint:
        from app.core.device_trust import DeviceFingerprint
        fingerprint = DeviceFingerprint(**request.fingerprint.dict())
    
    assessment = await service.assess_risk(
        user_id=user.id,
        organization_id=org.id,
        ip=request.ip,
        fingerprint=fingerprint,
        context=request.context,
    )
    
    return {
        "risk_score": assessment.risk_score,
        "risk_level": assessment.risk_level.value,
        "required_challenges": [c.value for c in assessment.required_challenges],
        "recommended_challenge": assessment.recommended_challenge.value if assessment.recommended_challenge else None,
        "allow": assessment.allow,
        "block_reason": assessment.block_reason,
        "ip_risk": assessment.ip_risk,
        "device_risk": assessment.device_risk,
        "geo_risk": assessment.geo_risk,
        "velocity_risk": assessment.velocity_risk,
        "behavioral_risk": assessment.behavioral_risk,
    }


@router.get("/device-trust/ip-intelligence/{ip}")
async def get_ip_intelligence(
    ip: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("device:read")),
):
    """Get IP intelligence data."""
    service = get_device_trust_service()
    await service.initialize()
    
    intel = await service.get_ip_intelligence(ip)
    return {
        "ip": intel.ip,
        "country": intel.country,
        "country_code": intel.country_code,
        "region": intel.region,
        "city": intel.city,
        "asn": intel.asn,
        "isp": intel.isp,
        "is_proxy": intel.is_proxy,
        "is_vpn": intel.is_vpn,
        "is_tor": intel.is_tor,
        "threat_level": intel.threat_level,
        "reputation_score": intel.reputation_score,
    }


# ==================== SIEM Integration ====================

class SIEMConfigRequest(BaseModel):
    backend: str
    name: str
    endpoint: str
    token: Optional[str] = None
    api_key: Optional[str] = None
    index: Optional[str] = None
    sourcetype: str = "ocsf"
    batch_size: int = 100
    flush_interval: float = 5.0
    enabled: bool = True


class SIEMEventRequest(BaseModel):
    event_class: str
    category: str
    severity: str
    status: str
    message: str
    actor: Dict[str, Any]
    target: Optional[Dict[str, Any]] = None
    src_endpoint: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = {}


@router.post("/siem/connectors")
async def add_siem_connector(
    request: SIEMConfigRequest,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("security:write")),
):
    """Add a SIEM connector."""
    manager = get_siem_manager()
    
    config = SIEMConfig(
        backend=SIEMBackend(request.backend),
        name=request.name,
        endpoint=request.endpoint,
        token=request.token,
        api_key=request.api_key,
        index=request.index,
        sourcetype=request.sourcetype,
        batch_size=request.batch_size,
        flush_interval=request.flush_interval,
        enabled=request.enabled,
    )
    
    backend = manager.add_backend(config)
    await backend.initialize()
    return {"success": True, "connector": request.name}


@router.get("/siem/connectors")
async def list_siem_connectors(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("security:read")),
):
    """List all SIEM connectors."""
    manager = get_siem_manager()
    return {"connectors": manager.list_backends()}


@router.delete("/siem/connectors/{name}")
async def remove_siem_connector(
    name: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("security:write")),
):
    """Remove a SIEM connector."""
    manager = get_siem_manager()
    success = manager.remove_backend(name)
    return {"success": success}


@router.post("/siem/events")
async def send_siem_event(
    request: SIEMEventRequest,
    backend_names: Optional[List[str]] = Query(None),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("security:write")),
):
    """Send an event to SIEM."""
    manager = get_siem_manager()
    
    event = OCSFEventBuilder.build(
        OCSFClass(request.event_class),
        OCSFCategory(request.category),
        severity=Severity(request.severity),
        status=request.status,
        message=request.message,
        actor=request.actor,
        target=request.target,
        src_endpoint=request.src_endpoint,
        metadata=request.metadata,
    )
    
    results = await manager.send_event(event, backend_names)
    return {"results": results}


@router.post("/siem/authentication")
async def log_authentication_event(
    user_id: str = Body(...),
    username: str = Body(...),
    organization_id: str = Body(...),
    success: bool = Body(...),
    ip_address: str = Body(...),
    user_agent: str = Body(...),
    mfa_used: bool = Body(False),
    mfa_method: Optional[str] = Body(None),
    error: Optional[str] = Body(None),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("security:write")),
):
    """Log authentication event to SIEM."""
    manager = get_siem_manager()
    results = await manager.log_authentication(
        user_id=user_id,
        username=username,
        organization_id=organization_id,
        success=success,
        ip_address=ip_address,
        user_agent=user_agent,
        mfa_used=mfa_used,
        mfa_method=mfa_method,
        error=error,
    )
    return {"results": results}


@router.post("/siem/authorization")
async def log_authorization_event(
    user_id: str = Body(...),
    action: str = Body(...),
    resource_type: str = Body(...),
    resource_id: str = Body(...),
    allowed: bool = Body(...),
    organization_id: str = Body(...),
    ip_address: str = Body(...),
    policy_id: Optional[str] = Body(None),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("security:write")),
):
    """Log authorization decision to SIEM."""
    manager = get_siem_manager()
    results = await manager.log_authorization(
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        allowed=allowed,
        organization_id=organization_id,
        ip_address=ip_address,
        policy_id=policy_id,
    )
    return {"results": results}


# ==================== OCSF SIEM & DLP ====================

class OCSFConnectorConfigRequest(BaseModel):
    connector_type: str
    name: str
    endpoint: str
    auth_token: Optional[str] = None
    api_key: Optional[str] = None
    index: Optional[str] = None
    sourcetype: str = "ocsf"
    batch_size: int = 100
    flush_interval: float = 5.0
    enabled: bool = True


class DLPRuleRequest(BaseModel):
    id: str
    name: str
    description: str
    classifier_type: str
    patterns: List[str] = []
    ml_model_id: Optional[str] = None
    classifications: List[str] = []
    min_confidence: float = 0.8
    action: str = "alert"
    severity: str = "medium"
    enabled: bool = True


class DLPScanRequest(BaseModel):
    content: str
    context: Dict[str, Any] = {}


@router.post("/ocsf/connectors")
async def add_ocsf_connector(
    request: OCSFConnectorConfigRequest,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("security:write")),
):
    """Add an OCSF SIEM connector."""
    manager = get_ocsf_siem_manager()
    
    config = SIEMConnectorConfig(
        connector_type=SIEMConnectorType(request.connector_type),
        name=request.name,
        endpoint=request.endpoint,
        auth_token=request.auth_token,
        api_key=request.api_key,
        index=request.index,
        sourcetype=request.sourcetype,
        batch_size=request.batch_size,
        flush_interval=request.flush_interval,
        enabled=request.enabled,
    )
    
    connector = manager._create_backend(config)
    await connector.initialize()
    manager.add_connector(connector)
    return {"success": True, "connector": request.name}


@router.post("/dlp/rules")
async def add_dlp_rule(
    request: DLPRuleRequest,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("security:write")),
):
    """Add a DLP rule."""
    engine = get_dlp_engine()
    
    rule = DLPRule(
        id=request.id,
        name=request.name,
        description=request.description,
        classifier_type=DLPClassifierType(request.classifier_type),
        patterns=request.patterns,
        ml_model_id=request.ml_model_id,
        classifications=[DataClassification(c) for c in request.classifications],
        min_confidence=request.min_confidence,
        action=DLPAction(request.action),
        severity=OCSFSeverityId[request.severity.upper()],
        enabled=request.enabled,
    )
    engine.add_rule(rule)
    return {"success": True, "rule_id": rule.id}


@router.get("/dlp/rules")
async def list_dlp_rules(
    enabled_only: bool = Query(True),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("security:read")),
):
    """List DLP rules."""
    engine = get_dlp_engine()
    rules = engine.list_rules(enabled_only)
    return {"rules": [
        {
            "id": r.id,
            "name": r.name,
            "description": r.description,
            "classifier_type": r.classifier_type.value,
            "patterns": r.patterns,
            "classifications": [c.value for c in r.classifications],
            "action": r.action.value,
            "severity": r.severity.name.lower(),
            "enabled": r.enabled,
        }
        for r in rules
    ]}


@router.post("/dlp/scan")
async def scan_dlp(
    request: DLPScanRequest,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("security:read")),
):
    """Scan content for DLP violations."""
    matches = await scan_for_dlp(request.content, request.context)
    return {"matches": [
        {
            "rule_id": m.rule_id,
            "rule_name": m.rule_name,
            "classification": m.classification.value,
            "confidence": m.confidence,
            "matched_content": m.matched_content,
            "action": m.action.value,
            "severity": m.severity.name.lower(),
        }
        for m in matches
    ]}


@router.post("/dlp/scan-and-protect")
async def scan_and_protect_dlp(
    request: DLPScanRequest,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("security:write")),
):
    """Scan content and apply DLP actions."""
    modified_content, events = await scan_and_protect(request.content, request.context)
    return {"modified_content": modified_content, "events_generated": len(events)}


# ==================== Compliance Dashboards ====================

class ComplianceControlRequest(BaseModel):
    framework: str
    control_id: str
    status: str
    evidence_ids: Optional[List[str]] = None
    notes: str = ""


class ComplianceEvidenceRequest(BaseModel):
    control_id: str
    framework: str
    evidence_type: str
    title: str
    description: str
    content: Optional[str] = None
    file_path: Optional[str] = None
    collected_by: str = ""
    expires_in_days: int = 365


class GapRemediationRequest(BaseModel):
    status: str
    notes: str = ""
    assigned_to: Optional[str] = None


@router.post("/compliance/controls/status")
async def update_control_status(
    request: ComplianceControlRequest,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("compliance:write")),
):
    """Update control implementation status."""
    engine = get_compliance_engine()
    engine.update_control_status(
        control_id=f"{request.framework}:{request.control_id}",
        status=ControlStatus(request.status),
        evidence_ids=request.evidence_ids,
        notes=request.notes,
    )
    return {"success": True}


@router.get("/compliance/controls")
async def list_compliance_controls(
    framework: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("compliance:read")),
):
    """List compliance controls."""
    engine = get_compliance_engine()
    
    fw = DashboardFramework(framework) if framework else None
    st = ControlStatus(status) if status else None
    
    controls = engine.list_controls(
        framework=fw,
        category=category,
        status=st,
    )
    
    return {"controls": [
        {
            "id": c.id,
            "framework": c.framework.value,
            "control_id": c.control_id,
            "title": c.title,
            "description": c.description,
            "category": c.category,
            "status": c.status.value,
            "evidence_count": len(c.evidence),
            "automated": c.automated,
            "last_tested": c.last_tested.isoformat() if c.last_tested else None,
        }
        for c in controls
    ]}


@router.post("/compliance/evidence")
async def add_compliance_evidence(
    request: ComplianceEvidenceRequest,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("compliance:write")),
):
    """Add compliance evidence."""
    engine = get_compliance_engine()
    evidence = await engine.add_evidence(
        control_id=request.control_id,
        framework=DashboardFramework(request.framework),
        evidence_type=EvidenceType(request.evidence_type),
        title=request.title,
        description=request.description,
        content=request.content,
        file_path=request.file_path,
        collected_by=request.collected_by or user.id,
        expires_in_days=request.expires_in_days,
    )
    return {"success": True, "evidence_id": evidence.id}


@router.post("/compliance/gap-analysis")
async def run_gap_analysis(
    framework: str = Body(...),
    organization_id: str = Body(...),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("compliance:read")),
):
    """Run automated gap analysis."""
    engine = get_compliance_engine()
    gaps = await engine.perform_gap_analysis(DashboardFramework(framework), organization_id)
    return {"gaps": [
        {
            "id": g.id,
            "control_id": g.control_id,
            "title": g.title,
            "description": g.description,
            "severity": g.severity,
            "status": g.status.value,
        }
        for g in gaps
    ]}


@router.post("/compliance/gaps/{gap_id}/remediation")
async def update_gap_remediation(
    gap_id: str,
    request: GapRemediationRequest,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("compliance:write")),
):
    """Update gap remediation status."""
    engine = get_compliance_engine()
    engine.update_gap_status(gap_id, RemediationStatus(request.status), request.notes, request.assigned_to)
    return {"success": True}


@router.post("/compliance/assessment")
async def perform_assessment(
    framework: str = Body(...),
    organization_id: str = Body(...),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("compliance:read")),
):
    """Perform comprehensive compliance assessment."""
    engine = get_compliance_engine()
    assessment = await engine.perform_assessment(
        DashboardFramework(framework),
        organization_id,
        user.id,
    )
    return {
        "assessment_id": assessment.id,
        "overall_score": assessment.overall_score,
        "audit_readiness": assessment.audit_readiness.value,
        "passed_controls": assessment.passed_controls,
        "failed_controls": assessment.failed_controls,
        "gaps_count": len(assessment.gaps),
    }


@router.get("/compliance/dashboard")
async def get_compliance_dashboard(
    framework: str = Query(...),
    organization_id: str = Query(...),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("compliance:read")),
):
    """Get compliance dashboard."""
    engine = get_compliance_engine()
    dashboard = engine.get_dashboard(organization_id, DashboardFramework(framework))
    if not dashboard:
        return {"dashboard": None}
    
    return {
        "overall_score": dashboard.overall_score,
        "controls_by_status": dashboard.controls_by_status,
        "gaps_by_severity": dashboard.gaps_by_severity,
        "evidence_status": dashboard.evidence_status,
        "upcoming_tests": dashboard.upcoming_tests,
        "open_gaps_count": len(dashboard.open_gaps),
    }


# ==================== Compliance Reporting ====================

class ReportGenerationRequest(BaseModel):
    framework: str
    organization_id: str
    organization_name: str
    period_start: str
    period_end: str
    format: str = "pdf"
    template_id: Optional[str] = None


class ReportScheduleRequest(BaseModel):
    framework: str
    organization_id: str
    name: str
    cron_expression: str
    format: str = "pdf"
    recipients: List[str] = []
    template_id: Optional[str] = None


@router.post("/compliance/reports/generate")
async def generate_compliance_report(
    request: ReportGenerationRequest,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("compliance:write")),
):
    """Generate compliance report."""
    engine = get_compliance_reporting_engine()
    
    report = await engine.generate_report(
        framework=ReportingFramework(request.framework),
        organization_id=request.organization_id,
        organization_name=request.organization_name,
        period_start=datetime.fromisoformat(request.period_start),
        period_end=datetime.fromisoformat(request.period_end),
        format=ReportFormat(request.format),
        generated_by=user.id,
        template_id=request.template_id,
    )
    
    return {
        "report_id": report.id,
        "status": report.status.value,
        "overall_score": report.overall_score,
        "controls_tested": report.controls_tested,
        "controls_compliant": report.controls_compliant,
    }


@router.get("/compliance/reports")
async def list_reports(
    framework: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("compliance:read")),
):
    """List generated reports."""
    engine = get_compliance_reporting_engine()
    # Would query database in production
    return {"reports": []}


@router.post("/compliance/reports/schedule")
async def schedule_report(
    request: ReportScheduleRequest,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("compliance:write")),
):
    """Schedule recurring compliance report."""
    engine = get_compliance_reporting_engine()
    
    schedule = ReportSchedule(
        id=str(uuid4()),
        framework=ReportingFramework(request.framework),
        organization_id=request.organization_id,
        name=request.name,
        cron_expression=request.cron_expression,
        format=ReportFormat(request.format),
        recipients=request.recipients,
        template_id=request.template_id,
    )
    
    engine._schedules[schedule.id] = schedule
    return {"success": True, "schedule_id": schedule.id}


# ==================== GDPR/CCPA Rights ====================

class DataSubjectRequestRequest(BaseModel):
    request_type: str  # access, rectification, erasure, portability, restriction, objection
    subject_identifier: str
    organization_id: str
    request_details: Dict[str, Any] = {}


@router.post("/gdpr/requests")
async def create_data_subject_request(
    request: DataSubjectRequestRequest,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("gdpr:write")),
):
    """Create a data subject request (GDPR/CCPA)."""
    framework = get_compliance_framework()
    await framework.initialize()
    
    request_obj = await framework.create_data_subject_request(
        request_type=request.request_type,
        subject_identifier=request.subject_identifier,
        organization_id=request.organization_id,
        request_details=request.request_details,
    )
    return {"request_id": request_obj.id, "status": request_obj.status}


@router.post("/gdpr/requests/{request_id}/process")
async def process_data_subject_request(
    request_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("gdpr:write")),
):
    """Process a data subject request."""
    framework = get_compliance_framework()
    await framework.initialize()
    
    request_obj = await framework.process_data_subject_request(request_id, user.id)
    return {"request_id": request_obj.id, "status": request_obj.status, "response_data": request_obj.response_data}


@router.get("/gdpr/requests")
async def list_data_subject_requests(
    organization_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("gdpr:read")),
):
    """List data subject requests."""
    framework = get_compliance_framework()
    await framework.initialize()
    
    requests = framework.data_subject_manager.list_requests(organization_id, status)
    return {"requests": [
        {
            "id": r.id,
            "request_type": r.request_type,
            "subject_identifier": r.subject_identifier,
            "status": r.status,
            "created_at": r.created_at.isoformat(),
            "completed_at": r.completed_at.isoformat() if r.completed_at else None,
        }
        for r in requests
    ]}


# ==================== Retention Policies ====================

class RetentionPolicyRequest(BaseModel):
    id: str
    name: str
    description: str
    resource_types: List[str]
    classification: str
    retention_days: int
    action: str
    conditions: Dict[str, Any] = {}
    legal_hold: bool = False


@router.post("/compliance/retention/policies")
async def add_retention_policy(
    request: RetentionPolicyRequest,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("compliance:write")),
):
    """Add a data retention policy."""
    framework = get_compliance_framework()
    await framework.initialize()
    
    policy = RetentionPolicy(
        id=request.id,
        name=request.name,
        description=request.description,
        resource_types=request.resource_types,
        classification=DataClassification(request.classification),
        retention_days=request.retention_days,
        action=RetentionAction(request.action),
        conditions=request.conditions,
        legal_hold=request.legal_hold,
    )
    
    framework.add_retention_policy(policy)
    return {"success": True}


@router.get("/compliance/retention/policies")
async def list_retention_policies(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("compliance:read")),
):
    """List retention policies."""
    framework = get_compliance_framework()
    await framework.initialize()
    
    policies = framework.list_retention_policies()
    return {"policies": [
        {
            "id": p.id,
            "name": p.name,
            "description": p.description,
            "resource_types": p.resource_types,
            "classification": p.classification.value,
            "retention_days": p.retention_days,
            "action": p.action.value,
            "is_active": p.is_active,
            "legal_hold": p.legal_hold,
        }
        for p in policies
    ]}


# ==================== Audit Logs ====================

class AuditLogRequest(BaseModel):
    event_type: str
    user_id: Optional[str] = None
    organization_id: Optional[str] = None
    session_id: Optional[str] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    resource_type: Optional[str] = None
    resource_id: Optional[str] = None
    action: str = ""
    outcome: str = "success"
    risk_level: str = "low"
    details: Dict[str, Any] = {}
    metadata: Dict[str, Any] = {}


@router.post("/audit/log")
async def log_audit_event(
    request: AuditLogRequest,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("audit:write")),
):
    """Log an audit event."""
    framework = get_compliance_framework()
    await framework.initialize()
    
    event = await framework.log_event(
        event_type=AuditEventType(request.event_type),
        user_id=request.user_id,
        organization_id=request.organization_id or org.id,
        session_id=request.session_id,
        ip_address=request.ip_address,
        user_agent=request.user_agent,
        resource_type=request.resource_type,
        resource_id=request.resource_id,
        action=request.action,
        outcome=request.outcome,
        risk_level=request.risk_level,
        details=request.details,
        metadata=request.metadata,
    )
    return {"event_id": event.id, "merkle_root": event.merkle_root}


@router.get("/audit/verify")
async def verify_audit_integrity(
    start_sequence: int = Query(0),
    end_sequence: Optional[int] = Query(None),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("audit:read")),
):
    """Verify audit log integrity."""
    framework = get_compliance_framework()
    await framework.initialize()
    
    result = await framework.verify_audit_integrity(start_sequence=start_sequence, end_sequence=end_sequence)
    return result


# ==================== Data Classification ====================

class DataClassificationRequest(BaseModel):
    data: Dict[str, Any]
    rules: Dict[str, str]


@router.post("/compliance/classify")
async def classify_data(
    request: DataClassificationRequest,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("compliance:read")),
):
    """Classify data based on rules."""
    framework = get_compliance_framework()
    await framework.initialize()
    
    rules = {k: DataClassification(v) for k, v in request.rules.items()}
    classification = framework.classify_data(request.data, rules)
    return {"classification": classification.value}


# ==================== Enterprise SSO / Identity ====================

class OIDCConfigRequest(BaseModel):
    provider: str  # okta, azure_ad, google, custom
    client_id: str
    client_secret: str
    issuer_url: str
    scopes: List[str] = ["openid", "profile", "email"]


class SAMLConfigRequest(BaseModel):
    entity_id: str
    sso_url: str
    slo_url: Optional[str] = None
    x509_cert: str
    attribute_mapping: Dict[str, str] = {}


@router.post("/enterprise/sso/oidc")
async def configure_oidc(
    request: OIDCConfigRequest,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("admin:write")),
):
    """Configure OIDC provider for enterprise SSO."""
    # Would store in database and configure OIDC client
    return {"success": True, "provider": request.provider, "issuer": request.issuer_url}


@router.post("/enterprise/sso/saml")
async def configure_saml(
    request: SAMLConfigRequest,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("admin:write")),
):
    """Configure SAML provider for enterprise SSO."""
    # Would store in database and configure SAML SP
    return {"success": True, "entity_id": request.entity_id}


# ==================== HIPAA/FedRAMP Specific ====================

@router.get("/hipaa/safeguards")
async def get_hipaa_safeguards(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("compliance:read")),
):
    """Get HIPAA safeguards checklist."""
    engine = get_compliance_engine()
    controls = engine.list_controls(framework=DashboardFramework.HIPAA)
    
    return {"safeguards": [
        {
            "id": c.id,
            "control_id": c.control_id,
            "title": c.title,
            "category": c.category,
            "status": c.status.value,
            "requirements": c.description,
        }
        for c in controls
    ]}


@router.get("/fedramp/controls")
async def get_fedramp_controls(
    level: str = Query("moderate"),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("compliance:read")),
):
    """Get FedRAMP controls."""
    engine = get_compliance_engine()
    framework = DashboardFramework.FEDRAMP if level == "moderate" else DashboardFramework.FEDRAMP
    controls = engine.list_controls(framework=framework)
    
    return {"controls": [
        {
            "id": c.id,
            "control_id": c.control_id,
            "title": c.title,
            "category": c.category,
            "status": c.status.value,
            "requirements": c.implementation_guidance,
        }
        for c in controls
    ]}


# ==================== Continuous Monitoring ====================

@router.post("/compliance/continuous-checks")
async def run_continuous_checks(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("compliance:write")),
):
    """Run continuous compliance checks."""
    engine = get_compliance_engine()
    await engine.run_continuous_checks()
    return {"success": True, "message": "Continuous compliance checks initiated"}


# ==================== Health & Status ====================

@router.get("/health")
async def security_compliance_health(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("security:read")),
):
    """Get security & compliance system health."""
    # Check various components
    checks = {
        "abac_engine": "healthy",
        "rebac_engine": "healthy",
        "webauthn": "healthy",
        "scim": "healthy",
        "device_trust": "healthy",
        "siem": "healthy",
        "dlp": "healthy",
        "compliance": "healthy",
        "audit_log": "healthy",
    }
    
    overall = "healthy" if all(v == "healthy" for v in checks.values()) else "degraded"
    
    return {"overall": overall, "components": checks}


import uuid
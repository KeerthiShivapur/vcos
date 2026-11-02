"""MFA, Device Trust, and Security Management API (Gate 26)."""

from datetime import datetime, timedelta
from typing import Any, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_client_ip, get_current_organization, get_current_user, require_permission
from app.db.database import get_db
from app.models.organization import Organization
from app.models.user import (
    User,
    MFAMethod,
    TrustedDevice,
    SecurityAuditEvent,
    OrganizationSecurityPolicy,
    AccessReview,
    AccessReviewItem,
)
from app.models.role import RolePermission, Permission
from app.services.mfa_service import mfa_service

router = APIRouter(prefix="/security", tags=["Security & Identity"])


# =============================================================================
# Request/Response Models
# =============================================================================

class TOTPSetupResponse(BaseModel):
    method_id: str
    provisioning_uri: str
    secret: str
    backup_codes: list[str]


class TOTPVerifyRequest(BaseModel):
    code: str = Field(..., min_length=6, max_length=6)
    method_id: Optional[str] = None


class TOTPSetupVerifyRequest(BaseModel):
    code: str = Field(..., min_length=6, max_length=6)
    method_id: str


class MFAMethodResponse(BaseModel):
    id: str
    method_type: str
    device_name: Optional[str] = None
    device_type: Optional[str] = None
    is_primary: bool
    is_verified: bool
    verified_at: Optional[datetime] = None
    last_used_at: Optional[datetime] = None
    use_count: int
    created_at: datetime


class PasskeyRegistrationStartResponse(BaseModel):
    challenge: str
    challenge_hash: str
    options: dict


class PasskeyRegistrationCompleteRequest(BaseModel):
    credential: dict
    challenge_hash: str
    device_name: Optional[str] = None


class PasskeyAuthenticationStartResponse(BaseModel):
    challenge: str
    challenge_hash: str
    options: dict


class PasskeyAuthenticationCompleteRequest(BaseModel):
    credential: dict
    challenge_hash: str


class BackupCodesResponse(BaseModel):
    backup_codes: list[str]


class TrustedDeviceResponse(BaseModel):
    id: str
    device_fingerprint: str
    device_name: str
    device_type: str
    browser: Optional[str] = None
    os: Optional[str] = None
    is_trusted: bool
    trusted_at: Optional[datetime] = None
    trust_expires_at: Optional[datetime] = None
    verification_method: Optional[str] = None
    last_seen_at: Optional[datetime] = None
    last_ip: Optional[str] = None
    created_at: datetime


class RevokeDeviceRequest(BaseModel):
    reason: Optional[str] = None


class SecurityAuditEventResponse(BaseModel):
    id: str
    event_type: str
    event_category: str
    severity: str
    actor_id: Optional[str] = None
    actor_email: Optional[str] = None
    target_type: Optional[str] = None
    target_id: Optional[str] = None
    ip_address: Optional[str] = None
    outcome: str
    risk_score: int
    risk_factors: list[str]
    details: dict
    occurred_at: datetime


class SecurityPolicyResponse(BaseModel):
    organization_id: str
    mfa_required: bool
    mfa_methods_allowed: list[str]
    mfa_grace_period_days: int
    session_idle_timeout_minutes: int
    session_max_duration_hours: int
    max_concurrent_sessions: int
    require_reauth_for_sensitive: bool
    sensitive_actions_require_reauth: list[str]
    device_trust_required: bool
    device_trust_duration_days: int
    max_trusted_devices: int
    auto_trust_on_mfa: bool
    password_min_length: int
    password_require_uppercase: bool
    password_require_lowercase: bool
    password_require_numbers: bool
    password_require_symbols: bool
    password_max_age_days: int
    password_history_count: int
    allowed_auth_methods: list[str]
    require_email_verification: bool
    block_disposable_emails: bool
    alert_on_failed_login_threshold: int
    alert_on_new_device: bool
    alert_on_privileged_action: bool
    security_event_retention_days: int
    audit_log_retention_days: int
    data_export_requires_approval: bool
    updated_by: Optional[str] = None
    updated_at: datetime


class SecurityPolicyUpdate(BaseModel):
    mfa_required: Optional[bool] = None
    mfa_methods_allowed: Optional[list[str]] = None
    mfa_grace_period_days: Optional[int] = None
    session_idle_timeout_minutes: Optional[int] = None
    session_max_duration_hours: Optional[int] = None
    max_concurrent_sessions: Optional[int] = None
    require_reauth_for_sensitive: Optional[bool] = None
    sensitive_actions_require_reauth: Optional[list[str]] = None
    device_trust_required: Optional[bool] = None
    device_trust_duration_days: Optional[int] = None
    max_trusted_devices: Optional[int] = None
    auto_trust_on_mfa: Optional[bool] = None
    password_min_length: Optional[int] = None
    password_require_uppercase: Optional[bool] = None
    password_require_lowercase: Optional[bool] = None
    password_require_numbers: Optional[bool] = None
    password_require_symbols: Optional[bool] = None
    password_max_age_days: Optional[int] = None
    password_history_count: Optional[int] = None
    allowed_auth_methods: Optional[list[str]] = None
    require_email_verification: Optional[bool] = None
    block_disposable_emails: Optional[bool] = None
    alert_on_failed_login_threshold: Optional[int] = None
    alert_on_new_device: Optional[bool] = None
    alert_on_privileged_action: Optional[bool] = None
    security_event_retention_days: Optional[int] = None
    audit_log_retention_days: Optional[int] = None
    data_export_requires_approval: Optional[bool] = None


class SecurityEventQuery(BaseModel):
    user_id: Optional[str] = None
    event_type: Optional[str] = None
    severity: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    limit: int = Field(100, ge=1, le=500)
    offset: int = Field(0, ge=0)


class AccessReviewCreateRequest(BaseModel):
    name: str
    scope_type: str
    scope_config: dict
    frequency: str = "quarterly"
    reviewer_id: Optional[str] = None


class AccessReviewItemDecisionRequest(BaseModel):
    decision: str = Field(..., pattern="^(approve|revoke|modify|defer)$")
    reason: str


# =============================================================================
# MFA - TOTP
# =============================================================================

@router.post("/mfa/totp/setup", response_model=TOTPSetupResponse)
async def setup_totp(
    request: Request,
    user: User = Depends(require_permission("security:mfa:manage")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Set up a new TOTP (authenticator app) MFA method."""
    result = await mfa_service.setup_totp(db, user=user)
    await db.commit()
    return result


@router.post("/mfa/totp/verify-setup", response_model=dict)
async def verify_totp_setup(
    request: TOTPSetupVerifyRequest,
    user: User = Depends(require_permission("security:mfa:manage")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Verify TOTP code during initial setup."""
    valid = await mfa_service.verify_totp_setup(db, user=user, code=request.code, method_id=request.method_id)
    await db.commit()
    return {"valid": valid}


@router.post("/mfa/totp/verify", response_model=dict)
async def verify_totp(
    request: TOTPVerifyRequest,
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Verify a TOTP code (for step-up authentication)."""
    valid = await mfa_service.verify_totp(db, user=user, code=request.code, method_id=request.method_id)
    return {"valid": valid}


@router.get("/mfa/methods", response_model=list[MFAMethodResponse])
async def list_mfa_methods(
    user: User = Depends(require_permission("security:mfa:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """List all MFA methods for the current user."""
    methods = await mfa_service.get_user_mfa_methods(db, user.id)
    return [
        MFAMethodResponse(
            id=m.id,
            method_type=m.method_type,
            device_name=m.device_name,
            device_type=m.device_type,
            is_primary=m.is_primary,
            is_verified=m.is_verified,
            verified_at=m.verified_at,
            last_used_at=m.last_used_at,
            use_count=m.use_count,
            created_at=m.created_at,
        )
        for m in methods
    ]


@router.delete("/mfa/methods/{method_id}", response_model=dict)
async def remove_mfa_method(
    method_id: str,
    user: User = Depends(require_permission("security:mfa:manage")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Remove an MFA method."""
    success = await mfa_service.remove_mfa_method(db, user=user, method_id=method_id)
    await db.commit()
    return {"success": success}


@router.post("/mfa/backup-codes/generate", response_model=BackupCodesResponse)
async def generate_backup_codes(
    method_id: str = Body(..., embed=True),
    user: User = Depends(require_permission("security:mfa:manage")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Generate new backup codes for TOTP."""
    codes = await mfa_service.generate_backup_codes(db, user=user, method_id=method_id)
    await db.commit()
    return {"backup_codes": codes}


# =============================================================================
# MFA - Passkeys/WebAuthn
# =============================================================================

@router.post("/mfa/passkey/register/start", response_model=PasskeyRegistrationStartResponse)
async def start_passkey_registration(
    device_name: Optional[str] = Body(None, embed=True),
    user: User = Depends(require_permission("security:mfa:manage")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Start WebAuthn passkey registration."""
    result = await mfa_service.start_passkey_registration(db, user=user, device_name=device_name)
    return result


@router.post("/mfa/passkey/register/complete", response_model=MFAMethodResponse)
async def complete_passkey_registration(
    request: PasskeyRegistrationCompleteRequest,
    user: User = Depends(require_permission("security:mfa:manage")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Complete WebAuthn passkey registration."""
    mfa_method = await mfa_service.complete_passkey_registration(
        db, user=user, credential=request.credential, challenge_hash=request.challenge_hash, device_name=request.device_name
    )
    await db.commit()
    return MFAMethodResponse(
        id=mfa_method.id,
        method_type=mfa_method.method_type,
        device_name=mfa_method.device_name,
        device_type=mfa_method.device_type,
        is_primary=mfa_method.is_primary,
        is_verified=mfa_method.is_verified,
        verified_at=mfa_method.verified_at,
        last_used_at=mfa_method.last_used_at,
        use_count=mfa_method.use_count,
        created_at=mfa_method.created_at,
    )


@router.post("/mfa/passkey/authenticate/start", response_model=PasskeyAuthenticationStartResponse)
async def start_passkey_authentication(
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Start WebAuthn passkey authentication."""
    result = await mfa_service.start_passkey_authentication(db, user=user)
    return result


@router.post("/mfa/passkey/authenticate/complete", response_model=dict)
async def complete_passkey_authentication(
    request: PasskeyAuthenticationCompleteRequest,
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Complete WebAuthn passkey authentication."""
    valid = await mfa_service.verify_passkey_authentication(
        db, user=user, credential=request.credential, challenge_hash=request.challenge_hash
    )
    return {"valid": valid}


# =============================================================================
# Device Trust
# =============================================================================

@router.get("/devices", response_model=list[TrustedDeviceResponse])
async def list_devices(
    include_revoked: bool = Query(False),
    user: User = Depends(require_permission("security:devices:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """List all trusted devices for the current user."""
    devices = await mfa_service.get_user_devices(db, user.id, include_revoked=include_revoked)
    return [
        TrustedDeviceResponse(
            id=d.id,
            device_fingerprint=d.device_fingerprint,
            device_name=d.device_name,
            device_type=d.device_type,
            browser=d.browser,
            os=d.os,
            is_trusted=d.is_trusted,
            trusted_at=d.trusted_at,
            trust_expires_at=d.trust_expires_at,
            verification_method=d.verification_method,
            last_seen_at=d.last_seen_at,
            last_ip=d.last_ip,
            created_at=d.created_at,
        )
        for d in devices
    ]


@router.post("/devices/{device_id}/revoke", response_model=dict)
async def revoke_device(
    device_id: str,
    request: RevokeDeviceRequest,
    user: User = Depends(require_permission("security:devices:manage")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Revoke a trusted device."""
    success = await mfa_service.revoke_device(
        db, user=user, device_id=device_id, revoked_by=user.id, reason=request.reason
    )
    await db.commit()
    return {"success": success}


@router.post("/devices/revoke-all", response_model=dict)
async def revoke_all_devices(
    user: User = Depends(require_permission("security:devices:manage")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Revoke all trusted devices for the current user."""
    count = await mfa_service.revoke_all_devices(db, user=user, revoked_by=user.id)
    await db.commit()
    return {"revoked_count": count}


@router.get("/devices/check", response_model=dict)
async def check_device_trust(
    device_fingerprint: str = Query(...),
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Check if a device is trusted."""
    trusted = await mfa_service.is_device_trusted(db, user_id=user.id, device_fingerprint=device_fingerprint)
    return {"trusted": trusted}


# =============================================================================
# Security Policies
# =============================================================================

@router.get("/policy", response_model=SecurityPolicyResponse)
async def get_security_policy(
    user: User = Depends(require_permission("security:policy:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Get organization security policy."""
    policy = await mfa_service.get_security_policy(db, org.id)
    if not policy:
        # Return defaults
        return SecurityPolicyResponse(
            organization_id=org.id,
            mfa_required=False,
            mfa_methods_allowed=["totp", "passkey"],
            mfa_grace_period_days=30,
            session_idle_timeout_minutes=60,
            session_max_duration_hours=24,
            max_concurrent_sessions=5,
            require_reauth_for_sensitive=True,
            sensitive_actions_require_reauth=[
                "user.delete", "role.assign", "permission.grant",
                "security.policy.update", "connector.configure", "data.export", "organization.delete"
            ],
            device_trust_required=False,
            device_trust_duration_days=90,
            max_trusted_devices=10,
            auto_trust_on_mfa=True,
            password_min_length=12,
            password_require_uppercase=True,
            password_require_lowercase=True,
            password_require_numbers=True,
            password_require_symbols=True,
            password_max_age_days=90,
            password_history_count=5,
            allowed_auth_methods=["password", "google", "microsoft"],
            require_email_verification=False,
            block_disposable_emails=True,
            alert_on_failed_login_threshold=5,
            alert_on_new_device=True,
            alert_on_privileged_action=True,
            security_event_retention_days=365,
            audit_log_retention_days=2555,
            data_export_requires_approval=True,
            updated_at=utcnow(),
        )
    return SecurityPolicyResponse(
        organization_id=policy.organization_id,
        mfa_required=policy.mfa_required,
        mfa_methods_allowed=policy.mfa_methods_allowed or [],
        mfa_grace_period_days=policy.mfa_grace_period_days,
        session_idle_timeout_minutes=policy.session_idle_timeout_minutes,
        session_max_duration_hours=policy.session_max_duration_hours,
        max_concurrent_sessions=policy.max_concurrent_sessions,
        require_reauth_for_sensitive=policy.require_reauth_for_sensitive,
        sensitive_actions_require_reauth=policy.sensitive_actions_require_reauth or [],
        device_trust_required=policy.device_trust_required,
        device_trust_duration_days=policy.device_trust_duration_days,
        max_trusted_devices=policy.max_trusted_devices,
        auto_trust_on_mfa=policy.auto_trust_on_mfa,
        password_min_length=policy.password_min_length,
        password_require_uppercase=policy.password_require_uppercase,
        password_require_lowercase=policy.password_require_lowercase,
        password_require_numbers=policy.password_require_numbers,
        password_require_symbols=policy.password_require_symbols,
        password_max_age_days=policy.password_max_age_days,
        password_history_count=policy.password_history_count,
        allowed_auth_methods=policy.allowed_auth_methods or [],
        require_email_verification=policy.require_email_verification,
        block_disposable_emails=policy.block_disposable_emails,
        alert_on_failed_login_threshold=policy.alert_on_failed_login_threshold,
        alert_on_new_device=policy.alert_on_new_device,
        alert_on_privileged_action=policy.alert_on_privileged_action,
        security_event_retention_days=policy.security_event_retention_days,
        audit_log_retention_days=policy.audit_log_retention_days,
        data_export_requires_approval=policy.data_export_requires_approval,
        updated_by=policy.updated_by,
        updated_at=policy.updated_at,
    )


@router.patch("/policy", response_model=SecurityPolicyResponse)
async def update_security_policy(
    update: SecurityPolicyUpdate,
    user: User = Depends(require_permission("security:policy:manage")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Update organization security policy."""
    update_data = update.model_dump(exclude_unset=True)
    policy = await mfa_service.create_or_update_security_policy(
        db, organization_id=org.id, updated_by=user.id, **update_data
    )
    await db.commit()
    return SecurityPolicyResponse(
        organization_id=policy.organization_id,
        mfa_required=policy.mfa_required,
        mfa_methods_allowed=policy.mfa_methods_allowed or [],
        mfa_grace_period_days=policy.mfa_grace_period_days,
        session_idle_timeout_minutes=policy.session_idle_timeout_minutes,
        session_max_duration_hours=policy.session_max_duration_hours,
        max_concurrent_sessions=policy.max_concurrent_sessions,
        require_reauth_for_sensitive=policy.require_reauth_for_sensitive,
        sensitive_actions_require_reauth=policy.sensitive_actions_require_reauth or [],
        device_trust_required=policy.device_trust_required,
        device_trust_duration_days=policy.device_trust_duration_days,
        max_trusted_devices=policy.max_trusted_devices,
        auto_trust_on_mfa=policy.auto_trust_on_mfa,
        password_min_length=policy.password_min_length,
        password_require_uppercase=policy.password_require_uppercase,
        password_require_lowercase=policy.password_require_lowercase,
        password_require_numbers=policy.password_require_numbers,
        password_require_symbols=policy.password_require_symbols,
        password_max_age_days=policy.password_max_age_days,
        password_history_count=policy.password_history_count,
        allowed_auth_methods=policy.allowed_auth_methods or [],
        require_email_verification=policy.require_email_verification,
        block_disposable_emails=policy.block_disposable_emails,
        alert_on_failed_login_threshold=policy.alert_on_failed_login_threshold,
        alert_on_new_device=policy.alert_on_new_device,
        alert_on_privileged_action=policy.alert_on_privileged_action,
        security_event_retention_days=policy.security_event_retention_days,
        audit_log_retention_days=policy.audit_log_retention_days,
        data_export_requires_approval=policy.data_export_requires_approval,
        updated_by=policy.updated_by,
        updated_at=policy.updated_at,
    )


# =============================================================================
# Security Events
# =============================================================================

@router.post("/events/query", response_model=list[SecurityAuditEventResponse])
async def query_security_events(
    query: SecurityEventQuery,
    user: User = Depends(require_permission("security:events:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Query security audit events."""
    events = await mfa_service.get_security_events(
        db,
        organization_id=org.id,
        user_id=query.user_id,
        event_type=query.event_type,
        severity=query.severity,
        start_date=query.start_date,
        end_date=query.end_date,
        limit=query.limit,
        offset=query.offset,
    )
    return [
        SecurityAuditEventResponse(
            id=e.id,
            event_type=e.event_type,
            event_category=e.event_category,
            severity=e.severity,
            actor_id=e.actor_id,
            actor_email=e.actor_email,
            target_type=e.target_type,
            target_id=e.target_id,
            ip_address=e.ip_address,
            outcome=e.outcome,
            risk_score=e.risk_score,
            risk_factors=e.risk_factors,
            details=e.details,
            occurred_at=e.occurred_at,
        )
        for e in events
    ]


# =============================================================================
# Session Security
# =============================================================================

@router.post("/session/check", response_model=dict)
async def check_session_policy(
    request: Request,
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Check if current session complies with security policy."""
    # Get current session from request (would need to extract from auth)
    # For now, return policy info
    policy = await mfa_service.get_security_policy(db, org.id)
    if not policy:
        return {"allowed": True, "policy": None}

    return {
        "allowed": True,
        "policy": {
            "session_idle_timeout_minutes": policy.session_idle_timeout_minutes,
            "session_max_duration_hours": policy.session_max_duration_hours,
            "max_concurrent_sessions": policy.max_concurrent_sessions,
        }
    }


@router.post("/session/reauth/check", response_model=dict)
async def check_reauth_required(
    action: str = Body(..., embed=True),
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Check if re-authentication is required for a sensitive action."""
    required = await mfa_service.check_reauth_required(db, user=user, action=action)
    return {"required": required, "action": action}


# =============================================================================
# Access Reviews
# =============================================================================

@router.post("/access-reviews", response_model=dict)
async def create_access_review(
    request: AccessReviewCreateRequest,
    user: User = Depends(require_permission("security:access_review:manage")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Create a new access review."""
    review = await mfa_service.create_access_review(
        db,
        organization_id=org.id,
        name=request.name,
        scope_type=request.scope_type,
        scope_config=request.scope_config,
        frequency=request.frequency,
        reviewer_id=request.reviewer_id or user.id,
    )
    await db.commit()
    return {"id": review.id, "name": review.name, "status": review.status, "due_at": review.due_at}


@router.post("/access-reviews/{review_id}/start", response_model=dict)
async def start_access_review(
    review_id: str,
    user: User = Depends(require_permission("security:access_review:manage")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Start an access review - populate items to review."""
    review = await mfa_service.start_access_review(db, review_id, user.id)
    await db.commit()
    if not review:
        raise HTTPException(404, "Review not found")
    return {"id": review.id, "status": review.status, "total_items": review.total_reviewed}


@router.post("/access-reviews/items/{item_id}/decide", response_model=dict)
async def decide_access_review_item(
    item_id: str,
    request: AccessReviewItemDecisionRequest,
    user: User = Depends(require_permission("security:access_review:manage")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Record a decision on an access review item."""
    success = await mfa_service.decide_access_review_item(
        db, item_id=item_id, decision=request.decision, reason=request.reason, decided_by=user.id
    )
    await db.commit()
    return {"success": success}


@router.post("/access-reviews/{review_id}/complete", response_model=dict)
async def complete_access_review(
    review_id: str,
    user: User = Depends(require_permission("security:access_review:manage")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Complete an access review."""
    review = await mfa_service.complete_access_review(db, review_id, user.id)
    await db.commit()
    if not review:
        raise HTTPException(404, "Review not found or not in progress")
    return {
        "id": review.id,
        "status": review.status,
        "completed_at": review.completed_at,
        "next_review_at": review.next_review_at,
        "summary": {
            "total": review.total_reviewed,
            "approved": review.approved,
            "revoked": review.revoked,
            "pending": review.pending_action,
        }
    }


# =============================================================================
# Exports
# =============================================================================

__all__ = ["router"]
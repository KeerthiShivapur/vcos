"""
Compliance Framework API Routes.

Provides endpoints for:
- Audit logging
- Data retention policies
- GDPR/CCPA data subject requests
- Compliance reporting (SOC2, ISO27001, GDPR)
- Data classification
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.api.deps import get_current_user, get_db
from app.core.compliance import (
    ComplianceFramework,
    AuditEventType,
    DataClassification,
    RetentionAction,
    RetentionPolicy,
    DataSubjectRequest,
    ComplianceReport,
    get_compliance_framework,
)
from app.models.user import User
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(tags=["Compliance Framework"])

logger = logging.getLogger(__name__)


# ==================== Models ====================

class AuditEventRequest(BaseModel):
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


class AuditEventResponse(BaseModel):
    id: str
    event_type: str
    timestamp: str
    user_id: Optional[str]
    organization_id: Optional[str]
    session_id: Optional[str]
    ip_address: Optional[str]
    user_agent: Optional[str]
    resource_type: Optional[str]
    resource_id: Optional[str]
    action: str
    outcome: str
    risk_level: str
    details: Dict[str, Any]
    metadata: Dict[str, Any]
    previous_hash: str
    merkle_root: str
    sequence_number: int


class RetentionPolicyCreate(BaseModel):
    name: str
    description: str
    resource_types: List[str]
    classification: str
    retention_days: int
    action: str
    conditions: Dict[str, Any] = {}
    legal_hold: bool = False


class RetentionPolicyResponse(BaseModel):
    id: str
    name: str
    description: str
    resource_types: List[str]
    classification: str
    retention_days: int
    action: str
    conditions: Dict[str, Any]
    is_active: bool
    created_at: str
    updated_at: str
    legal_hold: bool


class DataSubjectRequestCreate(BaseModel):
    request_type: str
    subject_identifier: str
    organization_id: str
    request_details: Dict[str, Any] = {}


class DataSubjectRequestResponse(BaseModel):
    id: str
    request_type: str
    subject_identifier: str
    organization_id: str
    status: str
    request_details: Dict[str, Any]
    response_data: Optional[Dict[str, Any]]
    created_at: str
    completed_at: Optional[str]
    assigned_to: Optional[str]


class ComplianceReportRequest(BaseModel):
    report_type: str
    organization_id: str
    period_start: str
    period_end: str


class ComplianceReportResponse(BaseModel):
    id: str
    report_type: str
    period_start: str
    period_end: str
    organization_id: str
    generated_at: str
    generated_by: str
    findings: List[Dict[str, Any]]
    metrics: Dict[str, Any]
    status: str


class DataClassificationRequest(BaseModel):
    data: Dict[str, Any]
    rules: Dict[str, str]


class IntegrityVerificationResponse(BaseModel):
    verified: bool
    total_events: int
    merkle_root: str
    checked_sequences: str


# ==================== Audit Logging ====================

@router.post("/compliance/audit", response_model=AuditEventResponse)
async def log_audit_event(
    request: AuditEventRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Log an audit event."""
    compliance = get_compliance_framework()
    
    try:
        event_type = AuditEventType(request.event_type)
    except ValueError:
        raise HTTPException(400, f"Invalid event type: {request.event_type}")
    
    event = await compliance.log_event(
        event_type=event_type,
        user_id=request.user_id or user.id,
        organization_id=request.organization_id or user.organization_id,
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
    
    return AuditEventResponse(
        id=event.id,
        event_type=event.event_type.value,
        timestamp=event.timestamp.isoformat(),
        user_id=event.user_id,
        organization_id=event.organization_id,
        session_id=event.session_id,
        ip_address=event.ip_address,
        user_agent=event.user_agent,
        resource_type=event.resource_type,
        resource_id=event.resource_id,
        action=event.action,
        outcome=event.outcome,
        risk_level=event.risk_level,
        details=event.details,
        metadata=event.metadata,
        previous_hash=event.previous_hash,
        merkle_root=event.merkle_root,
        sequence_number=event.sequence_number,
    )


@router.get("/compliance/audit/verify", response_model=IntegrityVerificationResponse)
async def verify_audit_integrity(
    start_sequence: int = Query(0, ge=0),
    end_sequence: Optional[int] = Query(None, ge=0),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Verify audit log integrity."""
    if not user.is_superuser:
        raise HTTPException(403, "Admin access required")
    
    compliance = get_compliance_framework()
    result = await compliance.verify_audit_integrity(
        start_sequence=start_sequence,
        end_sequence=end_sequence,
    )
    
    return IntegrityVerificationResponse(**result)


@router.get("/compliance/audit/stats")
async def get_audit_stats(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get audit logger statistics."""
    if not user.is_superuser:
        raise HTTPException(403, "Admin access required")
    
    compliance = get_compliance_framework()
    return compliance.audit_logger.get_stats()


# ==================== Data Retention ====================

@router.post("/compliance/retention/policies", response_model=RetentionPolicyResponse)
async def create_retention_policy(
    request: RetentionPolicyCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a data retention policy."""
    if not user.is_superuser:
        raise HTTPException(403, "Admin access required")
    
    compliance = get_compliance_framework()
    
    try:
        classification = DataClassification(request.classification)
        action = RetentionAction(request.action)
    except ValueError as e:
        raise HTTPException(400, f"Invalid value: {e}")
    
    policy = RetentionPolicy(
        id=str(uuid.uuid4()),
        name=request.name,
        description=request.description,
        resource_types=request.resource_types,
        classification=classification,
        retention_days=request.retention_days,
        action=action,
        conditions=request.conditions,
        legal_hold=request.legal_hold,
    )
    
    compliance.add_retention_policy(policy)
    
    return RetentionPolicyResponse(
        id=policy.id,
        name=policy.name,
        description=policy.description,
        resource_types=policy.resource_types,
        classification=policy.classification.value,
        retention_days=policy.retention_days,
        action=policy.action.value,
        conditions=policy.conditions,
        is_active=policy.is_active,
        created_at=policy.created_at.isoformat(),
        updated_at=policy.updated_at.isoformat(),
        legal_hold=policy.legal_hold,
    )


@router.get("/compliance/retention/policies", response_model=List[RetentionPolicyResponse])
async def list_retention_policies(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List data retention policies."""
    if not user.is_superuser:
        raise HTTPException(403, "Admin access required")
    
    compliance = get_compliance_framework()
    policies = compliance.list_retention_policies()
    
    return [
        RetentionPolicyResponse(
            id=p.id,
            name=p.name,
            description=p.description,
            resource_types=p.resource_types,
            classification=p.classification.value,
            retention_days=p.retention_days,
            action=p.action.value,
            conditions=p.conditions,
            is_active=p.is_active,
            created_at=p.created_at.isoformat(),
            updated_at=p.updated_at.isoformat(),
            legal_hold=p.legal_hold,
        )
        for p in policies
    ]


@router.delete("/compliance/retention/policies/{policy_id}")
async def delete_retention_policy(
    policy_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a retention policy."""
    if not user.is_superuser:
        raise HTTPException(403, "Admin access required")
    
    compliance = get_compliance_framework()
    success = compliance.retention_engine.remove_policy(policy_id)
    
    if not success:
        raise HTTPException(404, "Policy not found")
    
    return {"success": True}


# ==================== Data Subject Rights (GDPR/CCPA) ====================

@router.post("/compliance/dsr", response_model=DataSubjectRequestResponse)
async def create_data_subject_request(
    request: DataSubjectRequestCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a data subject request (GDPR/CCPA)."""
    compliance = get_compliance_framework()
    
    request_obj = await compliance.create_data_subject_request(
        request_type=request.request_type,
        subject_identifier=request.subject_identifier,
        organization_id=request.organization_id,
        request_details=request.request_details,
    )
    
    return DataSubjectRequestResponse(
        id=request_obj.id,
        request_type=request_obj.request_type,
        subject_identifier=request_obj.subject_identifier,
        organization_id=request_obj.organization_id,
        status=request_obj.status,
        request_details=request_obj.request_details,
        response_data=request_obj.response_data,
        created_at=request_obj.created_at.isoformat(),
        completed_at=request_obj.completed_at.isoformat() if request_obj.completed_at else None,
        assigned_to=request_obj.assigned_to,
    )


@router.post("/compliance/dsr/{request_id}/process", response_model=DataSubjectRequestResponse)
async def process_data_subject_request(
    request_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Process a data subject request."""
    if not user.is_superuser:
        raise HTTPException(403, "Admin access required")
    
    compliance = get_compliance_framework()
    
    request_obj = await compliance.process_data_subject_request(
        request_id=request_id,
        assigned_to=user.id,
    )
    
    return DataSubjectRequestResponse(
        id=request_obj.id,
        request_type=request_obj.request_type,
        subject_identifier=request_obj.subject_identifier,
        organization_id=request_obj.organization_id,
        status=request_obj.status,
        request_details=request_obj.request_details,
        response_data=request_obj.response_data,
        created_at=request_obj.created_at.isoformat(),
        completed_at=request_obj.completed_at.isoformat() if request_obj.completed_at else None,
        assigned_to=request_obj.assigned_to,
    )


@router.get("/compliance/dsr", response_model=List[DataSubjectRequestResponse])
async def list_data_subject_requests(
    organization_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List data subject requests."""
    if not user.is_superuser:
        raise HTTPException(403, "Admin access required")
    
    compliance = get_compliance_framework()
    requests = compliance.data_subject_manager.list_requests(
        organization_id=organization_id,
        status=status,
    )
    
    return [
        DataSubjectRequestResponse(
            id=r.id,
            request_type=r.request_type,
            subject_identifier=r.subject_identifier,
            organization_id=r.organization_id,
            status=r.status,
            request_details=r.request_details,
            response_data=r.response_data,
            created_at=r.created_at.isoformat(),
            completed_at=r.completed_at.isoformat() if r.completed_at else None,
            assigned_to=r.assigned_to,
        )
        for r in requests
    ]


@router.get("/compliance/dsr/{request_id}", response_model=DataSubjectRequestResponse)
async def get_data_subject_request(
    request_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get data subject request by ID."""
    compliance = get_compliance_framework()
    request_obj = compliance.data_subject_manager.get_request(request_id)
    
    if not request_obj:
        raise HTTPException(404, "Request not found")
    
    return DataSubjectRequestResponse(
        id=request_obj.id,
        request_type=request_obj.request_type,
        subject_identifier=request_obj.subject_identifier,
        organization_id=request_obj.organization_id,
        status=request_obj.status,
        request_details=request_obj.request_details,
        response_data=request_obj.response_data,
        created_at=request_obj.created_at.isoformat(),
        completed_at=request_obj.completed_at.isoformat() if request_obj.completed_at else None,
        assigned_to=request_obj.assigned_to,
    )


# ==================== Compliance Reporting ====================

@router.post("/compliance/reports", response_model=ComplianceReportResponse)
async def generate_compliance_report(
    request: ComplianceReportRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate a compliance report."""
    if not user.is_superuser:
        raise HTTPException(403, "Admin access required")
    
    compliance = get_compliance_framework()
    
    try:
        period_start = datetime.fromisoformat(request.period_start)
        period_end = datetime.fromisoformat(request.period_end)
    except ValueError:
        raise HTTPException(400, "Invalid date format. Use ISO format.")
    
    report = await compliance.generate_compliance_report(
        report_type=request.report_type,
        organization_id=request.organization_id,
        period_start=period_start,
        period_end=period_end,
        generated_by=user.id,
    )
    
    return ComplianceReportResponse(
        id=report.id,
        report_type=report.report_type,
        period_start=report.period_start.isoformat(),
        period_end=report.period_end.isoformat(),
        organization_id=report.organization_id,
        generated_at=report.generated_at.isoformat(),
        generated_by=report.generated_by,
        findings=report.findings,
        metrics=report.metrics,
        status=report.status,
    )


@router.get("/compliance/reports/types")
async def list_report_types(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List available compliance report types."""
    return {
        "report_types": [
            {"type": "soc2", "name": "SOC 2 Type II", "description": "Security, Availability, Confidentiality"},
            {"type": "iso27001", "name": "ISO 27001", "description": "Information Security Management"},
            {"type": "gdpr", "name": "GDPR", "description": "General Data Protection Regulation"},
            {"type": "hipaa", "name": "HIPAA", "description": "Health Insurance Portability"},
            {"type": "ccpa", "name": "CCPA", "description": "California Consumer Privacy Act"},
            {"type": "custom", "name": "Custom", "description": "Custom compliance report"},
        ]
    }


# ==================== Data Classification ====================

@router.post("/compliance/classify")
async def classify_data(
    request: DataClassificationRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Classify data based on rules."""
    compliance = get_compliance_framework()
    
    # Convert string rules to enum
    rules = {}
    for field, classification in request.rules.items():
        try:
            rules[field] = DataClassification(classification)
        except ValueError:
            raise HTTPException(400, f"Invalid classification: {classification}")
    
    classification = compliance.classify_data(request.data, rules)
    
    return {
        "classification": classification.value,
        "field_classifications": {
            field: rules.get(field, DataClassification.PUBLIC).value
            for field in request.data.keys()
        },
    }


# ==================== System ====================

@router.get("/compliance/stats")
async def get_compliance_stats(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get compliance framework statistics."""
    if not user.is_superuser:
        raise HTTPException(403, "Admin access required")
    
    compliance = get_compliance_framework()
    
    return {
        "audit": compliance.audit_logger.get_stats(),
        "retention_policies": len(compliance.retention_engine.list_policies()),
        "data_subject_requests": {
            "total": len(compliance.data_subject_manager.list_requests()),
            "pending": len(compliance.data_subject_manager.list_requests(status="pending")),
            "completed": len(compliance.data_subject_manager.list_requests(status="completed")),
        },
    }


import uuid
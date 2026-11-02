from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
from typing import Optional

from app.core.audit_log import (
    audit_log_manager, EventType, Severity,
    AuditEvent, MerkleTree, get_audit_log_manager
)
from app.api.deps import get_current_user, get_current_organization
from app.models.organization import Organization
from app.models.user import User


router = APIRouter(prefix="/audit", tags=["audit"])


class AuditEventResponse(BaseModel):
    id: str
    timestamp: datetime
    event_type: str
    severity: str
    actor_id: Optional[str]
    actor_type: str
    actor_ip: Optional[str]
    actor_user_agent: Optional[str]
    organization_id: Optional[str]
    resource_type: Optional[str]
    resource_id: Optional[str]
    action: Optional[str]
    outcome: str
    error_message: Optional[str]
    metadata: Dict[str, Any]
    correlation_id: Optional[str]
    causation_id: Optional[str]
    previous_hash: Optional[str]
    hash: Optional[str]
    merkle_proof: Optional[List[str]]


class AuditEventCreate(BaseModel):
    event_type: str
    actor_id: Optional[str] = None
    actor_type: str = "user"
    actor_ip: Optional[str] = None
    actor_user_agent: Optional[str] = None
    organization_id: Optional[str] = None
    resource_type: Optional[str] = None
    resource_id: Optional[str] = None
    action: Optional[str] = None
    outcome: str = "success"
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = {}
    severity: str = "info"


class AuditEventList(BaseModel):
    events: List[AuditEventResponse]
    total: int
    limit: int
    offset: int


class MerkleProofResponse(BaseModel):
    event_id: str
    leaf_hash: str
    proof: List[str]
    root_hash: str
    index: int


class VerificationResponse(BaseModel):
    event_id: str
    verified: bool
    verified_at: datetime


class ChainVerificationResponse(BaseModel):
    verified: bool
    checked_range: str
    checked_at: datetime


class StatsResponse(BaseModel):
    total_events: int
    buffer_size: int
    leaf_count: int
    current_root_hash: Optional[str]
    first_event_time: Optional[str]
    last_event_time: Optional[str]


@router.post("/events", response_model=AuditEventResponse, status_code=status.HTTP_201_CREATED)
async def create_audit_event(
    event: AuditEventCreate,
    current_user: User = Depends(get_current_user),
):
    manager = await get_audit_log_manager()
    event_id = await manager.log(
        event_type=EventType(event.event_type),
        actor_id=event.actor_id or current_user.id,
        actor_type=event.actor_type,
        actor_ip=event.actor_ip,
        actor_user_agent=event.actor_user_agent,
        organization_id=event.organization_id or current_user.organization_id,
        resource_type=event.resource_type,
        resource_id=event.resource_id,
        action=event.action,
        outcome=event.outcome,
        error_message=event.error_message,
        metadata=event.metadata,
        severity=Severity(event.severity),
    )
    
    audit_log = await get_audit_log_manager()
    event_obj = audit_log.audit_log.get_event(event_id)
    if not event_obj:
        raise HTTPException(status_code=404, detail="Event not found after creation")
    
    return AuditEventResponse(**event_obj.to_dict())


@router.get("/events", response_model=AuditEventList)
async def list_audit_events(
    start_time: Optional[datetime] = Query(None),
    end_time: Optional[datetime] = Query(None),
    event_type: Optional[str] = Query(None),
    actor_id: Optional[str] = Query(None),
    resource_type: Optional[str] = Query(None),
    resource_id: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    outcome: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
):
    manager = await get_audit_log_manager()
    audit_log = manager.audit_log
    
    event_type = EventType(event_type) if event_type else None
    severity_enum = Severity(severity) if severity else None
    
    events = audit_log.get_events(
        start_time=start_time,
        end_time=end_time,
        event_type=EventType(event_type) if event_type else None,
        actor_id=actor_id,
        resource_type=resource_type,
        resource_id=resource_id,
        severity=Severity(severity) if severity else None,
        outcome=outcome,
        limit=limit,
        offset=offset,
    )
    
    total = len(audit_log.events)
    for e in audit_log.events:
        if event_type and e.event_type.value != event_type:
            total -= 1
            continue
        if actor_id and e.actor_id != actor_id:
            total -= 1
            continue
        if resource_type and e.resource_type != resource_type:
            total -= 1
            continue
        if resource_id and e.resource_id != resource_id:
            total -= 1
            continue
        if severity and e.severity.value != severity:
            total -= 1
            continue
        if outcome and e.outcome != outcome:
            total -= 1
            continue
    
    return AuditEventList(
        events=[AuditEventResponse(**e.to_dict()) for e in events],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/events/{event_id}", response_model=AuditEventResponse)
async def get_audit_event(
    event_id: str,
    current_user: User = Depends(get_current_user),
):
    manager = await get_audit_log_manager()
    audit_log = manager.audit_log
    
    event = audit_log.get_event(event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    
    return AuditEventResponse(**event.to_dict())


@router.get("/events/{event_id}/proof", response_model=MerkleProofResponse)
async def get_merkle_proof(
    event_id: str,
    current_user: User = Depends(get_current_user),
):
    manager = await get_audit_log_manager()
    audit_log = manager.audit_log
    
    proof = audit_log.get_merkle_proof(event_id)
    if not proof:
        raise HTTPException(status_code=404, detail="Event not found or proof not available")
    
    return MerkleProofResponse(**proof)


@router.get("/events/{event_id}/verify", response_model=VerificationResponse)
async def verify_event(
    event_id: str,
    current_user: User = Depends(get_current_user),
):
    manager = await get_audit_log_manager()
    audit_log = manager.audit_log
    
    verified = audit_log.verify_event(event_id)
    
    return VerificationResponse(
        event_id=event_id,
        verified=verified,
        verified_at=datetime.utcnow(),
    )


@router.get("/chain/verify", response_model=ChainVerificationResponse)
async def verify_chain(
    start_index: int = Query(0, ge=0),
    end_index: Optional[int] = Query(None),
    current_user: User = Depends(get_current_user),
):
    manager = await get_audit_log_manager()
    audit_log = manager.audit_log
    
    verified = audit_log.verify_chain(start_index, end_index)
    
    return ChainVerificationResponse(
        verified=verified,
        checked_range=f"{start_index}-{end_index or 'end'}",
        checked_at=datetime.utcnow(),
    )


@router.get("/stats", response_model=StatsResponse)
async def get_audit_stats(
    current_user: User = Depends(get_current_user),
):
    manager = await get_audit_log_manager()
    audit_log = manager.audit_log
    
    return StatsResponse(**audit_log.get_stats())


@router.get("/root-hash")
async def get_current_root_hash(
    current_user: User = Depends(get_current_user),
):
    manager = await get_audit_log_manager()
    audit_log = manager.audit_log
    
    return {"root_hash": audit_log.get_current_root_hash()}


@router.get("/root-hash/{index}")
async def get_root_hash_at(
    index: int,
    current_user: User = Depends(get_current_user),
):
    manager = await get_audit_log_manager()
    audit_log = manager.audit_log
    
    root_hash = audit_log.get_root_hash_at(index)
    if root_hash is None:
        raise HTTPException(status_code=404, detail="Root hash not found for index")
    
    return {"index": index, "root_hash": root_hash}


@router.post("/export")
async def export_audit_log(
    start_time: Optional[datetime] = Query(None),
    end_time: Optional[datetime] = Query(None),
    event_type: Optional[str] = Query(None),
    format: str = Query("json", regex="^(json|csv)$"),
    current_user: User = Depends(get_current_user),
):
    manager = await get_audit_log_manager()
    audit_log = manager.audit_log
    
    event_type = EventType(event_type) if event_type else None
    
    events = audit_log.get_events(
        start_time=start_time,
        end_time=end_time,
        event_type=EventType(event_type) if event_type else None,
        limit=10000,
    )
    
    if format == "csv":
        import csv
        import io
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(
            "id", "timestamp", "event_type", "severity", "actor_id", "actor_type",
            "actor_ip", "organization_id", "resource_type", "resource_id",
            "action", "outcome", "error_message", "metadata", "correlation_id",
            "causation_id", "previous_hash", "hash"
        )
        for event in events:
            writer.writerow([
                event.id, event.timestamp.isoformat(), event.event_type.value,
                event.severity.value, event.actor_id, event.actor_type,
                event.actor_ip, event.organization_id, event.resource_type,
                event.resource_id, event.action, event.outcome, event.error_message,
                json.dumps(event.metadata), event.correlation_id, event.causation_id,
                event.previous_hash, event.hash
            ])
        
        from fastapi.responses import StreamingResponse
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=audit_log_{datetime.utcnow().isoformat()}.csv"}
        )
    
    return {"events": [e.to_dict() for e in events]}
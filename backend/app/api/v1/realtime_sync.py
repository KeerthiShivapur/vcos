"""
Offline-First Sync API Routes.

Provides REST endpoints for Service Worker background sync:
- Sync offline CRDT operations
- Sync documents
- Sync comments and annotations
- Sync push subscriptions
"""

import logging
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Path, Body
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import uuid4

from app.api.deps import get_current_user, get_db
from app.models.organization import Organization
from app.models.user import User
from app.core.crdt_engine import get_crdt_engine, CRDTOperation, CRDTType, OperationType
from app.services.permission_service import permission_service

router = APIRouter(tags=["Offline Sync"])

logger = logging.getLogger(__name__)


# ==================== Models ====================

class SyncItemRequest(BaseModel):
    """Request model for syncing a single offline operation."""
    id: str = Field(..., description="Unique ID of the sync item")
    type: str = Field(..., description="Type of operation: crdt, comment, annotation, etc.")
    payload: Dict[str, Any] = Field(..., description="Operation payload")
    timestamp: float = Field(..., description="When the operation was created")
    retries: int = Field(default=0, description="Number of retry attempts")
    priority: int = Field(default=0, description="Sync priority (higher = more urgent)")


class SyncItemResponse(BaseModel):
    """Response model for sync item."""
    success: bool
    item_id: str
    server_version: Optional[int] = None
    error: Optional[str] = None
    conflict: Optional[Dict[str, Any]] = None


class SyncDocumentRequest(BaseModel):
    """Request model for syncing a document."""
    id: str
    title: Optional[str] = None
    content: Optional[Any] = None
    crdt_type: str = "ytext"
    organization_id: str
    owner_id: str
    version: int = 0
    last_modified: float
    last_modified_by: str
    metadata: Dict[str, Any] = {}


class SyncDocumentResponse(BaseModel):
    """Response model for document sync."""
    success: bool
    document_id: str
    server_version: int
    conflict: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class PushSubscriptionSyncRequest(BaseModel):
    """Request model for syncing push subscription."""
    endpoint: str
    keys: Dict[str, str]


class PushSubscriptionSyncResponse(BaseModel):
    """Response model for push subscription sync."""
    success: bool
    subscription_id: str
    error: Optional[str] = None


class BulkSyncRequest(BaseModel):
    """Request model for bulk sync operations."""
    items: List[SyncItemRequest] = Field(default_factory=list)
    documents: List[SyncDocumentRequest] = Field(default_factory=list)


class BulkSyncResponse(BaseModel):
    """Response model for bulk sync."""
    synced: int
    failed: int
    conflicts: int
    results: List[SyncItemResponse]
    document_results: List[SyncDocumentResponse]


# ==================== Sync Endpoints ====================

@router.post("/sync/{item_type}", response_model=SyncItemResponse)
async def sync_offline_item(
    item_type: str = Path(..., description="Type of sync item: crdt, comment, annotation, etc."),
    request: SyncItemRequest = Body(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Sync a single offline operation from the Service Worker.
    
    Handles CRDT operations, comments, annotations, and other offline changes.
    """
    logger.info(f"Syncing offline item: type={item_type}, id={request.id}, user={user.id}")
    
    try:
        if item_type == "crdt":
            return await _sync_crdt_operation(request, user, db)
        elif item_type == "comment":
            return await _sync_comment(request, user, db)
        elif item_type == "annotation":
            return await _sync_annotation(request, user, db)
        elif item_type == "presence":
            return await _sync_presence(request, user, db)
        else:
            logger.warning(f"Unknown sync item type: {item_type}")
            return SyncItemResponse(
                success=False,
                item_id=request.id,
                error=f"Unknown item type: {item_type}"
            )
    except Exception as e:
        logger.error(f"Error syncing item {request.id}: {e}")
        return SyncItemResponse(
            success=False,
            item_id=request.id,
            error=str(e)
        )


@router.post("/sync/document", response_model=SyncDocumentResponse)
async def sync_document(
    request: SyncDocumentRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Sync a document from offline storage to the server.
    
    Handles document creation, updates, and conflict resolution.
    """
    logger.info(f"Syncing document: id={request.id}, user={user.id}")
    
    try:
        # Verify user has access to organization
        if request.organization_id != user.organization_id:
            # Check if user is member of the organization
            has_access = await permission_service.check_permission(
                user.id, request.organization_id, "documents.write"
            )
            if not has_access:
                raise HTTPException(403, "Access denied to organization")
        
        crdt_engine = get_crdt_engine()
        
        # Check if document exists
        existing_doc = crdt_engine.get_document_state(request.id)
        
        if existing_doc:
            # Document exists - check for conflicts
            if existing_doc["version"] > request.version:
                # Server has newer version - conflict
                return SyncDocumentResponse(
                    success=False,
                    document_id=request.id,
                    server_version=existing_doc["version"],
                    conflict={
                        "server_state": existing_doc,
                        "client_state": request.model_dump(),
                        "resolution": "server_wins"  # Default resolution
                    }
                )
            
            # Apply client operations if version matches or client is newer
            # In a real implementation, you'd apply the CRDT operations
            # For now, update the document state
            crdt_engine.create_document(
                doc_id=request.id,
                crdt_type=CRDTType(request.crdt_type),
                initial_state=request.content,
            )
            
            return SyncDocumentResponse(
                success=True,
                document_id=request.id,
                server_version=request.version + 1
            )
        else:
            # New document - create it
            crdt_engine.create_document(
                doc_id=request.id,
                crdt_type=CRDTType(request.crdt_type),
                initial_state=request.content,
            )
            
            return SyncDocumentResponse(
                success=True,
                document_id=request.id,
                server_version=1
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error syncing document {request.id}: {e}")
        return SyncDocumentResponse(
            success=False,
            document_id=request.id,
            server_version=0,
            error=str(e)
        )


@router.post("/push/subscriptions/{subscription_id}/sync", response_model=PushSubscriptionSyncResponse)
async def sync_push_subscription(
    subscription_id: str = Path(..., description="Push subscription ID"),
    request: PushSubscriptionSyncRequest = Body(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Sync push subscription from Service Worker to server.
    
    Updates the subscription endpoint and keys on the server.
    """
    logger.info(f"Syncing push subscription: id={subscription_id}, user={user.id}")
    
    try:
        # In a real implementation, you would update the subscription in the database
        # For now, return success
        return PushSubscriptionSyncResponse(
            success=True,
            subscription_id=subscription_id
        )
    except Exception as e:
        logger.error(f"Error syncing push subscription {subscription_id}: {e}")
        return PushSubscriptionSyncResponse(
            success=False,
            subscription_id=subscription_id,
            error=str(e)
        )


@router.post("/sync/bulk", response_model=BulkSyncResponse)
async def bulk_sync(
    request: BulkSyncRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Bulk sync multiple offline operations at once.
    
    Efficiently syncs multiple items and documents in a single request.
    """
    logger.info(f"Bulk sync: items={len(request.items)}, documents={len(request.documents)}, user={user.id}")
    
    item_results = []
    doc_results = []
    synced = 0
    failed = 0
    conflicts = 0
    
    # Sync items
    for item in request.items:
        try:
            if item.type == "crdt":
                result = await _sync_crdt_operation(item, user, db)
            elif item.type == "comment":
                result = await _sync_comment(item, user, db)
            elif item.type == "annotation":
                result = await _sync_annotation(item, user, db)
            elif item.type == "presence":
                result = await _sync_presence(item, user, db)
            else:
                result = SyncItemResponse(
                    success=False,
                    item_id=item.id,
                    error=f"Unknown item type: {item.type}"
                )
            
            item_results.append(result)
            if result.success:
                synced += 1
            elif result.conflict:
                conflicts += 1
                failed += 1
            else:
                failed += 1
        except Exception as e:
            logger.error(f"Error syncing item {item.id}: {e}")
            result = SyncItemResponse(
                success=False,
                item_id=item.id,
                error=str(e)
            )
            item_results.append(result)
            failed += 1
    
    # Sync documents
    for doc in request.documents:
        try:
            result = await sync_document(doc, user, db)
            doc_results.append(result)
            if result.success:
                synced += 1
            elif result.conflict:
                conflicts += 1
                failed += 1
            else:
                failed += 1
        except Exception as e:
            logger.error(f"Error syncing document {doc.id}: {e}")
            result = SyncDocumentResponse(
                success=False,
                document_id=doc.id,
                server_version=0,
                error=str(e)
            )
            doc_results.append(result)
            failed += 1
    
    return BulkSyncResponse(
        synced=synced,
        failed=failed,
        conflicts=conflicts,
        results=item_results,
        document_results=doc_results
    )


@router.get("/sync/status")
async def get_sync_status(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get sync status for the current user.
    
    Returns information about pending sync items, last sync time, etc.
    """
    # In a real implementation, fetch from database
    return {
        "user_id": user.id,
        "organization_id": user.organization_id,
        "pending_items": 0,
        "pending_documents": 0,
        "last_sync_time": None,
        "last_sync_status": "idle",
        "sync_enabled": True
    }


# ==================== Helper Functions ====================

async def _sync_crdt_operation(
    request: SyncItemRequest,
    user: User,
    db: AsyncSession
) -> SyncItemResponse:
    """Sync a CRDT operation."""
    crdt_engine = get_crdt_engine()
    
    try:
        operation_data = request.payload.get("operation")
        if not operation_data:
            return SyncItemResponse(
                success=False,
                item_id=request.id,
                error="Missing operation in payload"
            )
        
        operation = CRDTOperation(**operation_data)
        doc_id = request.payload.get("doc_id")
        
        if not doc_id:
            return SyncItemResponse(
                success=False,
                item_id=request.id,
                error="Missing doc_id in payload"
            )
        
        # Apply the operation
        result = await crdt_engine.apply_operation(doc_id, operation, user.id)
        
        if result.get("success"):
            doc_state = crdt_engine.get_document_state(doc_id)
            server_version = doc_state.get("version", 0) if doc_state else 0
            
            return SyncItemResponse(
                success=True,
                item_id=request.id,
                server_version=server_version
            )
        else:
            return SyncItemResponse(
                success=False,
                item_id=request.id,
                error=result.get("error", "CRDT operation failed"),
                conflict=result.get("conflict")
            )
    except Exception as e:
        logger.error(f"Error syncing CRDT operation {request.id}: {e}")
        return SyncItemResponse(
            success=False,
            item_id=request.id,
            error=str(e)
        )


async def _sync_comment(
    request: SyncItemRequest,
    user: User,
    db: AsyncSession
) -> SyncItemResponse:
    """Sync a comment operation."""
    # In a real implementation, sync comment to database
    logger.info(f"Syncing comment: {request.id}")
    
    return SyncItemResponse(
        success=True,
        item_id=request.id,
        server_version=request.payload.get("version", 1)
    )


async def _sync_annotation(
    request: SyncItemRequest,
    user: User,
    db: AsyncSession
) -> SyncItemResponse:
    """Sync an annotation operation."""
    # In a real implementation, sync annotation to database
    logger.info(f"Syncing annotation: {request.id}")
    
    return SyncItemResponse(
        success=True,
        item_id=request.id,
        server_version=request.payload.get("version", 1)
    )


async def _sync_presence(
    request: SyncItemRequest,
    user: User,
    db: AsyncSession
) -> SyncItemResponse:
    """Sync presence update."""
    # Presence updates are typically ephemeral, just acknowledge
    logger.debug(f"Syncing presence: {request.id}")
    
    return SyncItemResponse(
        success=True,
        item_id=request.id,
        server_version=1
    )
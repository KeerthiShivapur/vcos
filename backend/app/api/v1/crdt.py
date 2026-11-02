"""CRDT API Endpoints."""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Body, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.crdt import (
    CRDTManager,
    CRDTType,
    CRDTOperation,
    OperationType,
    get_crdt_manager,
)

router = APIRouter(prefix="/crdt", tags=["crdt"])


# =========================================================================
# Request/Response Models
# =========================================================================

class CRDTCreateRequest(BaseModel):
    crdt_id: str
    crdt_type: CRDTType
    initial_value: Any = None


class CRDTResponse(BaseModel):
    crdt_id: str
    crdt_type: str
    version: int
    last_modified: float
    data: Any


class OperationRequest(BaseModel):
    operation: OperationType
    key: str = ""
    value: Any = None
    author_id: str = ""
    metadata: Dict[str, Any] = {}


class LWWRegisterRequest(BaseModel):
    value: Any
    author_id: str


class LWWMapRequest(BaseModel):
    key: str
    value: Any
    author_id: str


class ORSetRequest(BaseModel):
    element: str
    author_id: str


class PNCounterRequest(BaseModel):
    author_id: str
    amount: int = 1


class MergeRequest(BaseModel):
    source_crdt_id: str
    target_crdt_id: str


# =========================================================================
# CRDT Management Endpoints
# =========================================================================

@router.post("/create", response_model=CRDTResponse, status_code=201)
async def create_crdt(request: CRDTCreateRequest):
    """Create a new CRDT."""
    manager = get_crdt_manager()
    
    if request.crdt_id in manager.crdts:
        raise HTTPException(status_code=400, detail=f"CRDT {request.crdt_id} already exists")
    
    crdt = manager.create_crdt(request.crdt_type, request.crdt_id)
    
    # Initialize with value if provided
    if request.initial_value is not None:
        if request.crdt_type == CRDTType.LWW_REGISTER:
            crdt = manager.crdts[request.crdt_id]
            if hasattr(crdt, 'set'):
                crdt.set(request.initial_value, "system")
        elif request.crdt_type == CRDTType.LWW_MAP and isinstance(request.initial_value, dict):
            crdt = manager.crdts[request.crdt_id]
            if hasattr(crdt, 'set'):
                for k, v in request.initial_value.items():
                    crdt.set(k, v, "system")
    
    crdt = manager.crdts[request.crdt_id]
    return CRDTResponse(
        crdt_id=crdt.crdt_id,
        crdt_type=crdt.crdt_type.value,
        version=crdt.version,
        last_modified=crdt.last_modified,
        data=crdt.get_state(),
    )


@router.get("", response_model=List[Dict[str, Any]])
async def list_crdts():
    """List all CRDTs."""
    manager = get_crdt_manager()
    return manager.list_crdts()


@router.get("/{crdt_id}", response_model=CRDTResponse)
async def get_crdt(crdt_id: str):
    """Get CRDT by ID."""
    manager = get_crdt_manager()
    crdt = manager.get_crdt(crdt_id)
    
    if not crdt:
        raise HTTPException(status_code=404, detail=f"CRDT {crdt_id} not found")
    
    return CRDTResponse(
        crdt_id=crdt.crdt_id,
        crdt_type=crdt.crdt_type.value,
        version=crdt.version,
        last_modified=crdt.last_modified,
        data=crdt.get_state(),
    )


@router.delete("/{crdt_id}")
async def delete_crdt(crdt_id: str):
    """Delete a CRDT."""
    manager = get_crdt_manager()
    success = manager.delete_crdt(crdt_id)
    
    if not success:
        raise HTTPException(status_code=404, detail=f"CRDT {crdt_id} not found")
    
    return {"success": True, "message": f"CRDT {crdt_id} deleted"}


@router.post("/{crdt_id}/merge")
async def merge_crdts(request: MergeRequest):
    """Merge source CRDT into target CRDT."""
    manager = get_crdt_manager()
    
    source = manager.get_crdt(request.source_crdt_id)
    target = manager.get_crdt(request.target_crdt_id)
    
    if not source or not target:
        raise HTTPException(status_code=404, detail="Source or target CRDT not found")
    
    if source.crdt_type != target.crdt_type:
        raise HTTPException(status_code=400, detail="Cannot merge CRDTs of different types")
    
    success = target.merge(source)
    
    return {
        "success": success,
        "message": "CRDTs merged" if success else "No changes to merge",
        "target": {
            "crdt_id": target.crdt_id,
            "version": target.version,
        },
    }


# =========================================================================
# LWW Register Endpoints
# =========================================================================

@router.post("/{crdt_id}/lww-register/set")
async def lww_register_set(crdt_id: str, request: LWWRegisterRequest):
    """Set value on LWW Register."""
    manager = get_crdt_manager()
    crdt = manager.get_crdt(crdt_id)
    
    if not crdt or not hasattr(crdt, 'set'):
        raise HTTPException(status_code=404, detail="LWW Register not found")
    
    op = crdt.set(request.value, request.author_id)
    return {"success": True, "operation_id": op.id, "version": crdt.version}


@router.post("/{crdt_id}/lww-register/delete")
async def lww_register_delete(crdt_id: str, author_id: str = Body(..., embed=True)):
    """Delete LWW Register value."""
    manager = get_crdt_manager()
    crdt = manager.get_crdt(crdt_id)
    
    if not crdt or not hasattr(crdt, 'delete'):
        raise HTTPException(status_code=404, detail="LWW Register not found")
    
    op = crdt.delete(author_id)
    return {"success": True, "operation_id": op.id, "version": crdt.version}


@router.get("/{crdt_id}/lww-register/get")
async def lww_register_get(crdt_id: str):
    """Get LWW Register value."""
    manager = get_crdt_manager()
    crdt = manager.get_crdt(crdt_id)
    
    if not crdt or not hasattr(crdt, 'get'):
        raise HTTPException(status_code=404, detail="LWW Register not found")
    
    return {"value": crdt.get(), "version": crdt.version}


# =========================================================================
# LWW Map Endpoints
# =========================================================================

@router.post("/{crdt_id}/lww-map/set")
async def lww_map_set(crdt_id: str, request: LWWMapRequest):
    """Set key-value on LWW Map."""
    manager = get_crdt_manager()
    crdt = manager.get_crdt(crdt_id)
    
    if not crdt or not hasattr(crdt, 'set'):
        raise HTTPException(status_code=404, detail="LWW Map not found")
    
    op = crdt.set(request.key, request.value, request.author_id)
    return {"success": True, "operation_id": op.id, "version": crdt.version}


@router.post("/{crdt_id}/lww-map/delete")
async def lww_map_delete(crdt_id: str, key: str = Body(..., embed=True), author_id: str = Body(..., embed=True)):
    """Delete key from LWW Map."""
    manager = get_crdt_manager()
    crdt = manager.get_crdt(crdt_id)
    
    if not crdt or not hasattr(crdt, 'delete'):
        raise HTTPException(status_code=404, detail="LWW Map not found")
    
    op = crdt.delete(key, author_id)
    return {"success": True, "operation_id": op.id, "version": crdt.version}


@router.get("/{crdt_id}/lww-map/get")
async def lww_map_get(crdt_id: str, key: str = Query(...)):
    """Get value from LWW Map."""
    manager = get_crdt_manager()
    crdt = manager.get_crdt(crdt_id)
    
    if not crdt or not hasattr(crdt, 'get'):
        raise HTTPException(status_code=404, detail="LWW Map not found")
    
    value = crdt.get(key)
    return {"value": value, "version": crdt.version}


@router.get("/{crdt_id}/lww-map/keys")
async def lww_map_keys(crdt_id: str):
    """Get all keys from LWW Map."""
    manager = get_crdt_manager()
    crdt = manager.get_crdt(crdt_id)
    
    if not crdt or not hasattr(crdt, 'keys'):
        raise HTTPException(status_code=404, detail="LWW Map not found")
    
    return {"keys": crdt.keys(), "version": crdt.version}


@router.get("/{crdt_id}/lww-map/items")
async def lww_map_items(crdt_id: str):
    """Get all key-value pairs from LWW Map."""
    manager = get_crdt_manager()
    crdt = manager.get_crdt(crdt_id)
    
    if not crdt or not hasattr(crdt, 'items'):
        raise HTTPException(status_code=404, detail="LWW Map not found")
    
    return {"items": crdt.items(), "version": crdt.version}


# =========================================================================
# OR-Set Endpoints
# =========================================================================

@router.post("/{crdt_id}/or-set/add")
async def or_set_add(crdt_id: str, request: ORSetRequest):
    """Add element to OR-Set."""
    manager = get_crdt_manager()
    crdt = manager.get_crdt(crdt_id)
    
    if not crdt or not hasattr(crdt, 'add'):
        raise HTTPException(status_code=404, detail="OR-Set not found")
    
    op = crdt.add(request.element, request.author_id)
    return {"success": True, "operation_id": op.id, "version": crdt.version}


@router.post("/{crdt_id}/or-set/remove")
async def or_set_remove(crdt_id: str, request: ORSetRequest):
    """Remove element from OR-Set."""
    manager = get_crdt_manager()
    crdt = manager.get_crdt(crdt_id)
    
    if not crdt or not hasattr(crdt, 'remove'):
        raise HTTPException(status_code=404, detail="OR-Set not found")
    
    op = crdt.remove(request.element, request.author_id)
    return {"success": True, "operation_id": op.id, "version": crdt.version}


@router.get("/{crdt_id}/or-set/contains")
async def or_set_contains(crdt_id: str, element: str = Query(...)):
    """Check if element is in OR-Set."""
    manager = get_crdt_manager()
    crdt = manager.get_crdt(crdt_id)
    
    if not crdt or not hasattr(crdt, 'contains'):
        raise HTTPException(status_code=404, detail="OR-Set not found")
    
    return {"contains": crdt.contains(element), "version": crdt.version}


@router.get("/{crdt_id}/or-set/elements")
async def or_set_elements(crdt_id: str):
    """Get all elements in OR-Set."""
    manager = get_crdt_manager()
    crdt = manager.get_crdt(crdt_id)
    
    if not crdt or not hasattr(crdt, 'elements'):
        raise HTTPException(status_code=404, detail="OR-Set not found")
    
    return {"elements": crdt.elements(), "version": crdt.version}


# =========================================================================
# PN Counter Endpoints
# =========================================================================

@router.post("/{crdt_id}/pn-counter/increment")
async def pn_counter_increment(crdt_id: str, request: PNCounterRequest):
    """Increment PN Counter."""
    manager = get_crdt_manager()
    crdt = manager.get_crdt(crdt_id)
    
    if not crdt or not hasattr(crdt, 'increment'):
        raise HTTPException(status_code=404, detail="PN Counter not found")
    
    op = crdt.increment(request.author_id, request.amount)
    return {"success": True, "operation_id": op.id, "value": crdt.value(), "version": crdt.version}


@router.post("/{crdt_id}/pn-counter/decrement")
async def pn_counter_decrement(crdt_id: str, request: PNCounterRequest):
    """Decrement PN Counter."""
    manager = get_crdt_manager()
    crdt = manager.get_crdt(crdt_id)
    
    if not crdt or not hasattr(crdt, 'decrement'):
        raise HTTPException(status_code=404, detail="PN Counter not found")
    
    op = crdt.decrement(request.author_id, request.amount)
    return {"success": True, "operation_id": op.id, "value": crdt.value(), "version": crdt.version}


@router.get("/{crdt_id}/pn-counter/value")
async def pn_counter_value(crdt_id: str):
    """Get PN Counter value."""
    manager = get_crdt_manager()
    crdt = manager.get_crdt(crdt_id)
    
    if not crdt or not hasattr(crdt, 'value'):
        raise HTTPException(status_code=404, detail="PN Counter not found")
    
    return {"value": crdt.value(), "version": crdt.version}


# =========================================================================
# Operations History
# =========================================================================

@router.get("/{crdt_id}/operations")
async def get_operations(crdt_id: str, limit: int = Query(100, ge=1, le=1000)):
    """Get operations history for a CRDT."""
    manager = get_crdt_manager()
    crdt = manager.get_crdt(crdt_id)
    
    if not crdt:
        raise HTTPException(status_code=404, detail=f"CRDT {crdt_id} not found")
    
    operations = crdt.operations[-limit:] if crdt.operations else []
    return {
        "operations": [
            {
                "id": op.id,
                "crdt_type": op.crdt_type.value,
                "operation": op.operation.value,
                "key": op.key,
                "value": op.value,
                "timestamp": op.timestamp,
                "author_id": op.author_id,
                "version": op.version,
                "metadata": op.metadata,
            }
            for op in operations
        ],
        "total": len(crdt.operations),
    }
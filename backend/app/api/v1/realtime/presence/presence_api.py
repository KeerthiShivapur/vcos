from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field
from datetime import datetime
import json
import asyncio
from collections import defaultdict

router = APIRouter(prefix="/presence", tags=["presence"])

class PresenceData(BaseModel):
    user_id: str
    user_name: str
    user_color: str
    cursor: Optional[Dict[str, float]] = None
    selection: Optional[Dict[str, int]] = None
    last_active: datetime = Field(default_factory=datetime.utcnow)
    document_id: str

class CursorPosition(BaseModel):
    x: float
    y: float

class SelectionRange(BaseModel):
    start: int
    end: int

class PresenceUpdate(BaseModel):
    user_id: str
    user_name: str
    user_color: str
    cursor: Optional[CursorPosition] = None
    selection: Optional[SelectionRange] = None
    document_id: str

class ConflictResolutionRequest(BaseModel):
    document_id: str
    user_id: str
    operation_type: str
    position: int
    content: str
    expected_version: int
    base_version: int

class ConflictResolutionResponse(BaseModel):
    resolved: bool
    resolved_content: str
    resolved_version: int
    conflict_details: Optional[str] = None

class DocumentVersion(BaseModel):
    document_id: str
    version: int
    content: str
    updated_at: datetime
    updated_by: str

class PresenceManager:
    def __init__(self):
        self.active_users: Dict[str, Dict[str, PresenceData]] = defaultdict(dict)
        self.document_versions: Dict[str, DocumentVersion] = {}
        self.pending_operations: Dict[str, List[Dict]] = defaultdict(list)
        self.operation_lock = asyncio.Lock()
    
    async def update_presence(self, presence: PresenceUpdate) -> PresenceData:
        presence_data = PresenceData(
            user_id=presence.user_id,
            user_name=presence.user_name,
            user_color=presence.user_color,
            cursor=presence.cursor.dict() if presence.cursor else None,
            selection=presence.selection.dict() if presence.selection else None,
            document_id=presence.document_id,
        )
        self.active_users[presence.document_id][presence.user_id] = presence_data
        return presence_data
    
    async def remove_presence(self, document_id: str, user_id: str):
        if document_id in self.active_users and user_id in self.active_users[document_id]:
            del self.active_users[document_id][user_id]
    
    async def get_presence(self, document_id: str) -> List[PresenceData]:
        return list(self.active_users.get(document_id, {}).values())
    
    async def get_document_version(self, document_id: str) -> DocumentVersion:
        if document_id not in self.document_versions:
            self.document_versions[document_id] = DocumentVersion(
                document_id=document_id,
                version=0,
                content="",
                updated_at=datetime.utcnow(),
                updated_by="system"
            )
        return self.document_versions[document_id]
    
    async def apply_operation(self, operation: ConflictResolutionRequest) -> ConflictResolutionResponse:
        async with self.operation_lock:
            doc_version = await self.get_document_version(operation.document_id)
            
            if operation.expected_version != doc_version.version:
                return ConflictResolutionResponse(
                    resolved=False,
                    resolved_content=doc_version.content,
                    resolved_version=doc_version.version,
                    conflict_details=f"Version mismatch: expected {operation.expected_version}, current {doc_version.version}"
                )
            
            if operation.operation_type == "insert":
                new_content = (
                    doc_version.content[:operation.position] + 
                    operation.content + 
                    doc_version.content[operation.position:]
                )
            elif operation.operation_type == "delete":
                new_content = (
                    doc_version.content[:operation.position] + 
                    doc_version.content[operation.position + len(operation.content):]
                )
            else:
                return ConflictResolutionResponse(
                    resolved=False,
                    resolved_content=doc_version.content,
                    resolved_version=doc_version.version,
                    conflict_details=f"Unknown operation type: {operation.operation_type}"
                )
            
            doc_version.content = new_content
            doc_version.version += 1
            doc_version.updated_at = datetime.utcnow()
            doc_version.updated_by = operation.user_id
            
            return ConflictResolutionResponse(
                resolved=True,
                resolved_content=new_content,
                resolved_version=doc_version.version,
                conflict_details=None
            )
    
    async def get_operation_history(self, document_id: str) -> List[Dict]:
        return self.pending_operations.get(document_id, [])

presence_manager = PresenceManager()

@router.post("/update", response_model=PresenceData)
async def update_presence(presence: PresenceUpdate):
    return await presence_manager.update_presence(presence)

@router.delete("/remove/{document_id}/{user_id}")
async def remove_presence(document_id: str, user_id: str):
    await presence_manager.remove_presence(document_id, user_id)
    return {"success": True}

@router.get("/list/{document_id}", response_model=List[PresenceData])
async def list_presence(document_id: str):
    return await presence_manager.get_presence(document_id)

@router.post("/conflict/resolve", response_model=ConflictResolutionResponse)
async def resolve_conflict(operation: ConflictResolutionRequest):
    return await presence_manager.apply_operation(operation)

@router.get("/version/{document_id}", response_model=DocumentVersion)
async def get_document_version(document_id: str):
    return await presence_manager.get_document_version(document_id)

@router.get("/history/{document_id}")
async def get_operation_history(document_id: str):
    return await presence_manager.get_operation_history(document_id)

class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, Dict[str, WebSocket]] = defaultdict(dict)
        self.user_info: Dict[str, Dict[str, Any]] = {}
    
    async def connect(self, websocket: WebSocket, document_id: str, user_id: str, user_name: str, user_color: str):
        await websocket.accept()
        self.active_connections[document_id][user_id] = websocket
        self.user_info[user_id] = {
            "user_id": user_id,
            "user_name": user_name,
            "user_color": user_color,
            "document_id": document_id,
        }
        await self.broadcast_presence(document_id)
    
    def disconnect(self, document_id: str, user_id: str):
        if document_id in self.active_connections and user_id in self.active_connections[document_id]:
            del self.active_connections[document_id][user_id]
            if user_id in self.user_info:
                del self.user_info[user_id]
    
    async def send_personal_message(self, message: dict, document_id: str, user_id: str):
        if document_id in self.active_connections and user_id in self.active_connections[document_id]:
            await self.active_connections[document_id][user_id].send_json(message)
    
    async def broadcast(self, message: dict, document_id: str, exclude_user: Optional[str] = None):
        if document_id in self.active_connections:
            for user_id, connection in self.active_connections[document_id].items():
                if user_id != exclude_user:
                    try:
                        await connection.send_json(message)
                    except:
                        pass
    
    async def broadcast_presence(self, document_id: str):
        if document_id in self.active_connections:
            presence_list = []
            for user_id, info in self.user_info.items():
                if info.get("document_id") == document_id:
                    presence_list.append({
                        "user_id": info["user_id"],
                        "user_name": info["user_name"],
                        "user_color": info["user_color"],
                    })
            
            message = {
                "type": "presence_update",
                "payload": {
                    "users": presence_list,
                    "timestamp": datetime.utcnow().isoformat(),
                }
            }
            
            await self.broadcast(message, document_id)

manager = ConnectionManager()

@router.websocket("/ws/{document_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    document_id: str,
    user_id: str = Query(...),
    user_name: str = Query(...),
    user_color: str = Query(...)
):
    await manager.connect(websocket, document_id, user_id, user_name, user_color)
    try:
        while True:
            data = await websocket.receive_json()
            message_type = data.get("type")
            
            if message_type == "cursor_update":
                await manager.broadcast({
                    "type": "cursor_update",
                    "payload": {
                        "user_id": user_id,
                        "user_name": manager.user_info.get(user_id, {}).get("user_name", "Unknown"),
                        "user_color": manager.user_info.get(user_id, {}).get("user_color", "#000000"),
                        "cursor": data.get("cursor"),
                        "selection": data.get("selection"),
                    }
                }, document_id, exclude_user=user_id)
            
            elif message_type == "text_operation":
                await manager.broadcast({
                    "type": "text_operation",
                    "payload": {
                        "user_id": user_id,
                        "operation": data.get("operation"),
                    }
                }, document_id, exclude_user=user_id)
            
            elif message_type == "presence_update":
                await manager.broadcast_presence(document_id)
    
    except WebSocketDisconnect:
        manager.disconnect(document_id, user_id)
        await manager.broadcast_presence(document_id)
    except Exception as e:
        print(f"WebSocket error: {e}")
        manager.disconnect(document_id, user_id)
        await manager.broadcast_presence(document_id)
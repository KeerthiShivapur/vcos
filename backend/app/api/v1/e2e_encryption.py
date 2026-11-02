"""
E2E Encryption API Routes

Provides endpoints for:
- Identity key management
- Prekey bundle management
- Session creation and management
- Encrypted CRDT operations
- Key rotation and access control
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.api.deps import get_current_user, get_db
from app.core.e2e_encryption import (
    DoubleRatchet,
    EncryptedCRDT,
    KeyManager,
    KeyPair,
    PreKeyBundle,
    SessionState,
    get_key_manager,
    init_e2e_encryption,
)
from app.models.user import User
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(tags=["E2E Encryption"])

logger = logging.getLogger(__name__)


# ==================== Models ====================

class IdentityKeyResponse(BaseModel):
    key_id: str
    public_key: str
    key_type: str
    created_at: float
    expires_at: Optional[float] = None


class PreKeyBundleResponse(BaseModel):
    identity_key: str
    signed_prekey: str
    signed_prekey_signature: str
    onetime_prekeys: List[str]
    registration_id: int


class SessionCreateRequest(BaseModel):
    recipient_id: str


class SessionResponse(BaseModel):
    session_id: str
    local_identity_key: str
    remote_identity_key: str
    root_key: str
    message_number_send: int
    message_number_recv: int
    created_at: float


class EncryptRequest(BaseModel):
    session_id: str
    plaintext: str
    associated_data: Optional[str] = None


class EncryptResponse(BaseModel):
    header: Dict[str, Any]
    ciphertext: str
    mac: str


class DecryptRequest(BaseModel):
    session_id: str
    header: Dict[str, Any]
    ciphertext: str
    mac: str
    associated_data: Optional[str] = None


class DocumentKeyRequest(BaseModel):
    document_id: str


class DocumentKeyResponse(BaseModel):
    document_id: str
    has_access: bool
    key: Optional[str] = None


class DocumentKeyShareRequest(BaseModel):
    document_id: str
    recipient_id: str


class DocumentKeyShareResponse(BaseModel):
    success: bool
    encrypted_key: Optional[str] = None


class DocumentOperationEncryptRequest(BaseModel):
    document_id: str
    operation: Dict[str, Any]


class DocumentOperationEncryptResponse(BaseModel):
    encrypted: str


class DocumentOperationDecryptRequest(BaseModel):
    document_id: str
    encrypted: str


class DocumentOperationDecryptResponse(BaseModel):
    operation: Dict[str, Any]


class GrantAccessRequest(BaseModel):
    document_id: str
    user_id: str


class RevokeAccessRequest(BaseModel):
    document_id: str
    user_id: str


class RotateKeyRequest(BaseModel):
    document_id: str


class KeyRotationScheduleRequest(BaseModel):
    document_id: str
    interval_hours: int = 24


class KeyStatsResponse(BaseModel):
    total_users: int
    total_sessions: int
    total_documents: int
    pending_rotations: int


# ==================== Identity Keys ====================

@router.post("/e2e/identity", response_model=IdentityKeyResponse)
async def create_identity_key(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create or get user's identity key"""
    key_manager = get_key_manager()
    
    # Initialize user if not exists
    await key_manager.initialize_user(user.id)
    
    identity = key_manager.identity_keys.get(user.id)
    if not identity:
        raise HTTPException(500, "Failed to create identity key")
    
    return IdentityKeyResponse(
        key_id=identity.key_id,
        public_key=base64.b64encode(identity.public_key).decode(),
        key_type=identity.key_type.value,
        created_at=identity.created_at,
        expires_at=identity.expires_at,
    )


@router.get("/e2e/identity", response_model=IdentityKeyResponse)
async def get_identity_key(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get user's identity key"""
    key_manager = get_key_manager()
    
    identity = key_manager.identity_keys.get(user.id)
    if not identity:
        raise HTTPException(404, "Identity key not found")
    
    return IdentityKeyResponse(
        key_id=identity.key_id,
        public_key=base64.b64encode(identity.public_key).decode(),
        key_type=identity.key_type.value,
        created_at=identity.created_at,
        expires_at=identity.expires_at,
    )


# ==================== Prekey Bundles ====================

@router.post("/e2e/prekeys", response_model=PreKeyBundleResponse)
async def create_prekey_bundle(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create or refresh user's prekey bundle"""
    key_manager = get_key_manager()
    
    bundle = await key_manager.initialize_user(user.id)
    
    return PreKeyBundleResponse(
        identity_key=base64.b64encode(bundle.identity_key).decode(),
        signed_prekey=base64.b64encode(bundle.signed_prekey).decode(),
        signed_prekey_signature=base64.b64encode(bundle.signed_prekey_signature).decode(),
        onetime_prekeys=[base64.b64encode(k).decode() for k in bundle.onetime_prekeys],
        registration_id=bundle.registration_id,
    )


@router.get("/e2e/prekeys", response_model=PreKeyBundleResponse)
async def get_prekey_bundle(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get user's prekey bundle"""
    key_manager = get_key_manager()
    
    bundle = key_manager.get_prekey_bundle(user.id)
    if not bundle:
        raise HTTPException(404, "Prekey bundle not found")
    
    return PreKeyBundleResponse(
        identity_key=base64.b64encode(bundle.identity_key).decode(),
        signed_prekey=base64.b64encode(bundle.signed_prekey).decode(),
        signed_prekey_signature=base64.b64encode(bundle.signed_prekey_signature).decode(),
        onetime_prekeys=[base64.b64encode(k).decode() for k in bundle.onetime_prekeys],
        registration_id=bundle.registration_id,
    )


@router.get("/e2e/prekeys/{target_user_id}", response_model=PreKeyBundleResponse)
async def get_user_prekey_bundle(
    target_user_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get another user's prekey bundle for session initiation"""
    key_manager = get_key_manager()
    
    bundle = key_manager.get_prekey_bundle(target_user_id)
    if not bundle:
        raise HTTPException(404, "Prekey bundle not found")
    
    return PreKeyBundleResponse(
        identity_key=base64.b64encode(bundle.identity_key).decode(),
        signed_prekey=base64.b64encode(bundle.signed_prekey).decode(),
        signed_prekey_signature=base64.b64encode(bundle.signed_prekey_signature).decode(),
        onetime_prekeys=[base64.b64encode(k).decode() for k in bundle.onetime_prekeys],
        registration_id=bundle.registration_id,
    )


# ==================== Session Management ====================

@router.post("/e2e/sessions", response_model=SessionResponse)
async def create_session(
    request: SessionCreateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create E2E session with another user"""
    key_manager = get_key_manager()
    
    try:
        session = await key_manager.create_session(user.id, request.recipient_id)
    except ValueError as e:
        raise HTTPException(404, str(e))
    
    return SessionResponse(
        session_id=session.session_id,
        local_identity_key=base64.b64encode(session.local_identity.public_key).decode(),
        remote_identity_key=base64.b64encode(session.remote_identity).decode(),
        root_key=base64.b64encode(session.root_key).decode(),
        message_number_send=session.message_number_send,
        message_number_recv=session.message_number_recv,
        created_at=session.created_at,
    )


@router.get("/e2e/sessions", response_model=List[SessionResponse])
async def list_sessions(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List user's active sessions"""
    key_manager = get_key_manager()
    
    sessions = []
    for session in key_manager.double_ratchet.sessions.values():
        sessions.append(SessionResponse(
            session_id=session.session_id,
            local_identity_key=base64.b64encode(session.local_identity.public_key).decode(),
            remote_identity_key=base64.b64encode(session.remote_identity).decode(),
            root_key=base64.b64encode(session.root_key).decode(),
            message_number_send=session.message_number_send,
            message_number_recv=session.message_number_recv,
            created_at=session.created_at,
        ))
    
    return sessions


@router.get("/e2e/sessions/{session_id}", response_model=SessionResponse)
async def get_session(
    session_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get session details"""
    key_manager = get_key_manager()
    
    session = key_manager.double_ratchet.get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    
    return SessionResponse(
        session_id=session.session_id,
        local_identity_key=base64.b64encode(session.local_identity.public_key).decode(),
        remote_identity_key=base64.b64encode(session.remote_identity).decode(),
        root_key=base64.b64encode(session.root_key).decode(),
        message_number_send=session.message_number_send,
        message_number_recv=session.message_number_recv,
        created_at=session.created_at,
    )


@router.delete("/e2e/sessions/{session_id}")
async def delete_session(
    session_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a session"""
    key_manager = get_key_manager()
    
    key_manager.double_ratchet.remove_session(session_id)
    return {"success": True}


# ==================== Message Encryption ====================

@router.post("/e2e/encrypt", response_model=EncryptResponse)
async def encrypt_message(
    request: EncryptRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Encrypt a message using session"""
    key_manager = get_key_manager()
    
    session = key_manager.double_ratchet.get_session(request.session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    
    encrypted = key_manager.double_ratchet.encrypt(
        session,
        request.plaintext.encode(),
        request.associated_data.encode() if request.associated_data else b"",
    )
    
    return EncryptResponse(
        header={
            "sender_registration_id": encrypted.header.sender_registration_id,
            "sender_ephemeral": base64.b64encode(encrypted.header.sender_ephemeral).decode(),
            "message_number": encrypted.header.message_number,
            "previous_chain_length": encrypted.header.previous_chain_length,
        },
        ciphertext=base64.b64encode(encrypted.ciphertext).decode(),
        mac=base64.b64encode(encrypted.mac).decode(),
    )


@router.post("/e2e/decrypt", response_model=Dict[str, str])
async def decrypt_message(
    request: DecryptRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Decrypt a message"""
    key_manager = get_key_manager()
    
    session = key_manager.double_ratchet.get_session(request.session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    
    # Reconstruct encrypted message
    from app.core.e2e_encryption import EncryptedMessage, MessageHeader
    encrypted = EncryptedMessage(
        header=MessageHeader(
            sender_registration_id=request.header.get("sender_registration_id", 0),
            sender_ephemeral=base64.b64decode(request.header["sender_ephemeral"]),
            message_number=request.header["message_number"],
            previous_chain_length=request.header.get("previous_chain_length", 0),
        ),
        ciphertext=base64.b64decode(request.ciphertext),
        mac=base64.b64decode(request.mac),
    )
    
    plaintext = key_manager.double_ratchet.decrypt(
        session,
        encrypted,
        request.associated_data.encode() if request.associated_data else b"",
    )
    
    return {"plaintext": plaintext.decode()}


# ==================== Document Keys ====================

@router.get("/e2e/documents/{document_id}/key", response_model=DocumentKeyResponse)
async def get_document_key(
    document_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get document encryption key for user"""
    key_manager = get_key_manager()
    
    try:
        key = await key_manager.get_document_key(document_id, user.id)
        return DocumentKeyResponse(
            document_id=document_id,
            has_access=True,
            key=base64.b64encode(key).decode(),
        )
    except PermissionError:
        return DocumentKeyResponse(
            document_id=document_id,
            has_access=False,
        )


@router.post("/e2e/documents/{document_id}/share", response_model=DocumentKeyShareResponse)
async def share_document_key(
    document_id: str,
    request: DocumentKeyShareRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Share document key with another user"""
    key_manager = get_key_manager()
    
    # Verify user has access
    try:
        await key_manager.get_document_key(document_id, user.id)
    except PermissionError:
        raise HTTPException(403, "No access to document")
    
    # Share key with recipient
    # This would require both users to have sessions
    # For now, grant access
    key_manager.grant_access(document_id, request.recipient_id)
    
    return DocumentKeyShareResponse(success=True)


@router.post("/e2e/documents/operations/encrypt", response_model=DocumentOperationEncryptResponse)
async def encrypt_document_operation(
    request: DocumentOperationEncryptRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Encrypt a CRDT operation"""
    key_manager = get_key_manager()
    
    # Get user's session for the document
    # For simplicity, using a placeholder session
    from app.core.e2e_encryption import SessionState
    session = SessionState(
        session_id="doc-" + request.document_id,
        local_identity=key_manager.double_ratchet.generate_identity_key(),
        remote_identity=b"\x00" * 32,
        root_key=b"\x00" * 32,
        chain_key_send=b"\x00" * 32,
        chain_key_recv=b"\x00" * 32,
    )
    
    encrypted = key_manager.encrypted_crdt.encrypt_operation(
        request.document_id,
        request.operation,
        session,
    )
    
    return DocumentOperationEncryptResponse(
        encrypted=base64.b64encode(encrypted).decode(),
    )


@router.post("/e2e/documents/operations/decrypt", response_model=DocumentOperationDecryptResponse)
async def decrypt_document_operation(
    request: DocumentOperationDecryptRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Decrypt a CRDT operation"""
    key_manager = get_key_manager()
    
    session = SessionState(
        session_id="doc-" + request.document_id,
        local_identity=key_manager.double_ratchet.generate_identity_key(),
        remote_identity=b"\x00" * 32,
        root_key=b"\x00" * 32,
        chain_key_send=b"\x00" * 32,
        chain_key_recv=b"\x00" * 32,
    )
    
    operation = key_manager.encrypted_crdt.decrypt_operation(
        request.document_id,
        base64.b64decode(request.encrypted),
        session,
    )
    
    return DocumentOperationDecryptResponse(operation=operation)


# ==================== Access Control ====================

@router.post("/e2e/documents/access/grant")
async def grant_document_access(
    request: GrantAccessRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Grant document access to user"""
    key_manager = get_key_manager()
    
    # Verify user has access
    try:
        await key_manager.get_document_key(request.document_id, user.id)
    except PermissionError:
        raise HTTPException(403, "No access to document")
    
    key_manager.grant_access(request.document_id, request.user_id)
    return {"success": True}


@router.post("/e2e/documents/access/revoke")
async def revoke_document_access(
    request: RevokeAccessRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Revoke document access from user"""
    key_manager = get_key_manager()
    
    # Verify user has access
    try:
        await key_manager.get_document_key(request.document_id, user.id)
    except PermissionError:
        raise HTTPException(403, "No access to document")
    
    key_manager.revoke_access(request.document_id, request.user_id)
    return {"success": True}


# ==================== Key Rotation ====================

@router.post("/e2e/documents/keys/rotate")
async def rotate_document_key(
    request: RotateKeyRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Rotate document encryption key"""
    key_manager = get_key_manager()
    
    # Verify user has access
    try:
        await key_manager.get_document_key(request.document_id, user.id)
    except PermissionError:
        raise HTTPException(403, "No access to document")
    
    await key_manager.rotate_keys(request.document_id, user.id)
    return {"success": True}


@router.post("/e2e/documents/keys/schedule")
async def schedule_key_rotation(
    request: KeyRotationScheduleRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Schedule automatic key rotation"""
    key_manager = get_key_manager()
    
    # Verify user has access
    try:
        await key_manager.get_document_key(request.document_id, user.id)
    except PermissionError:
        raise HTTPException(403, "No access to document")
    
    key_manager.schedule_rotation(request.document_id, request.interval_hours)
    return {"success": True}


# ==================== Stats ====================

@router.get("/e2e/stats", response_model=KeyStatsResponse)
async def get_key_stats(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get key management statistics"""
    key_manager = get_key_manager()
    
    return KeyStatsResponse(
        total_users=len(key_manager.identity_keys),
        total_sessions=len(key_manager.double_ratchet.sessions),
        total_documents=len(key_manager.document_keys),
        pending_rotations=len(key_manager.key_rotation_schedule),
    )


import base64
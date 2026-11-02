"""FIDO2/WebAuthn API Router."""

from typing import List, Optional
from fastapi import APIRouter, Body, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.core.fido2 import (
    WebAuthnManager,
    WebAuthnCredential,
    get_webauthn_manager,
)

router = APIRouter(prefix="/webauthn", tags=["webauthn"])


# =========================================================================
# Request/Response Models
# =========================================================================

class StartRegistrationRequest(BaseModel):
    user_id: str
    username: str
    display_name: str


class StartRegistrationResponse(BaseModel):
    state_id: str
    public_key: dict


class CompleteRegistrationRequest(BaseModel):
    state_id: str
    credential: dict


class StartAuthenticationRequest(BaseModel):
    user_id: Optional[str] = None
    username: Optional[str] = None


class StartAuthenticationResponse(BaseModel):
    state_id: str
    public_key: dict


class CompleteAuthenticationRequest(BaseModel):
    state_id: str
    credential: dict


class CredentialResponse(BaseModel):
    credential_id: str
    user_id: str
    public_key: str
    sign_count: int
    aaguid: Optional[str] = None
    transports: List[str] = []
    created_at: float
    last_used: float
    backup_eligible: bool
    backup_state: bool


# =========================================================================
# Registration Endpoints
# =========================================================================

@router.post("/registration/start", response_model=StartRegistrationResponse)
async def start_registration(
    request: StartRegistrationRequest,
    webauthn: WebAuthnManager = Depends(get_webauthn_manager),
):
    """Start WebAuthn registration ceremony."""
    # Get existing credentials to exclude
    existing_creds = webauthn.get_user_credentials(request.user_id)
    exclude_credentials = [c.credential_id for c in existing_creds]
    
    result = await webauthn.start_registration(
        user_id=request.user_id,
        username=request.username,
        display_name=request.display_name,
        exclude_credentials=exclude_credentials,
    )
    
    return StartRegistrationResponse(**result)


@router.post("/registration/complete", response_model=CredentialResponse)
async def complete_registration(
    request: CompleteRegistrationRequest,
    webauthn: WebAuthnManager = Depends(get_webauthn_manager),
):
    """Complete WebAuthn registration ceremony."""
    credential = await webauthn.complete_registration(
        state_id=request.state_id,
        credential=request.credential,
    )
    
    return WebAuthnManager.credential_to_json(credential)


# =========================================================================
# Authentication Endpoints
# =========================================================================

@router.post("/authentication/start", response_model=StartAuthenticationResponse)
async def start_authentication(
    request: StartAuthenticationRequest,
    webauthn: WebAuthnManager = Depends(get_webauthn_manager),
):
    """Start WebAuthn authentication ceremony."""
    result = await webauthn.start_authentication(
        user_id=request.user_id,
        username=request.username,
    )
    
    return StartAuthenticationResponse(**result)


@router.post("/authentication/complete", response_model=CredentialResponse)
async def complete_authentication(
    request: CompleteAuthenticationRequest,
    webauthn: WebAuthnManager = Depends(get_webauthn_manager),
):
    """Complete WebAuthn authentication ceremony."""
    credential = await webauthn.complete_authentication(
        state_id=request.state_id,
        credential=request.credential,
    )
    
    return WebAuthnManager.credential_to_json(credential)


# =========================================================================
# Credential Management Endpoints
# =========================================================================

@router.get("/credentials", response_model=List[CredentialResponse])
async def list_credentials(
    user_id: str,
    webauthn: WebAuthnManager = Depends(get_webauthn_manager),
):
    """List all credentials for a user."""
    credentials = webauthn.get_user_credentials(user_id)
    return [WebAuthnManager.credential_to_json(c) for c in credentials]


@router.delete("/credentials/{credential_id}")
async def delete_credential(
    credential_id: str,
    user_id: str,
    webauthn: WebAuthnManager = Depends(get_webauthn_manager),
):
    """Delete a credential."""
    import base64
    try:
        credential_id_bytes = base64.urlsafe_b64decode(credential_id + "==")
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid credential ID")
    
    success = webauthn.delete_credential(user_id, credential_id_bytes)
    if not success:
        raise HTTPException(status_code=404, detail="Credential not found")
    
    return {"success": True, "message": "Credential deleted"}


@router.get("/credentials/{credential_id}", response_model=CredentialResponse)
async def get_credential(
    credential_id: str,
    webauthn: WebAuthnManager = Depends(get_webauthn_manager),
):
    """Get credential by ID."""
    import base64
    try:
        credential_id_bytes = base64.urlsafe_b64decode(credential_id + "==")
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid credential ID")
    
    cred = webauthn.get_credential(credential_id_bytes)
    if not cred:
        raise HTTPException(status_code=404, detail="Credential not found")
    
    return WebAuthnManager.credential_to_json(cred)


@router.get("/rp-info")
async def get_rp_info(
    webauthn: WebAuthnManager = Depends(get_webauthn_manager),
):
    """Get relying party information."""
    return {
        "rp_id": webauthn.rp_id,
        "rp_name": webauthn.rp_name,
        "origin": webauthn.origin,
    }
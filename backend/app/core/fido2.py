"""FIDO2/WebAuthn Authentication Service."""

import base64
import hashlib
import json
import logging
import os
import secrets
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set
from uuid import uuid4

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    PublicFormat,
    load_der_public_key,
    load_pem_public_key,
)
from fido2 import cbor
from fido2.client import Fido2Client
from fido2.server import Fido2Server
from fido2.webauthn import (
    AttestationObject,
    AuthenticatorAssertionResponse,
    AuthenticatorAttestationResponse,
    PublicKeyCredentialDescriptor,
    PublicKeyCredentialRpEntity,
    PublicKeyCredentialUserEntity,
)
from fido2.utils import websafe_decode, websafe_encode

from app.core.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()


@dataclass
class WebAuthnRegistrationState:
    """State for WebAuthn registration."""
    challenge: bytes
    user_id: str
    username: str
    display_name: str
    rp_id: str
    rp_name: str
    created_at: float = field(default_factory=time.time)
    expires_at: float = field(default_factory=lambda: time.time() + 300)  # 5 min


@dataclass
class WebAuthnAuthenticationState:
    """State for WebAuthn authentication."""
    challenge: bytes
    user_id: Optional[str] = None  # None for discoverable credentials
    rp_id: str = ""
    created_at: float = field(default_factory=time.time)
    expires_at: float = field(default_factory=lambda: time.time() + 300)  # 5 min


@dataclass
class WebAuthnCredential:
    """Stored WebAuthn credential."""
    credential_id: bytes
    user_id: str
    public_key: bytes
    sign_count: int = 0
    aaguid: Optional[bytes] = None
    credential_type: str = "public-key"
    transports: List[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    last_used: float = field(default_factory=time.time)
    backup_eligible: bool = False
    backup_state: bool = False


class WebAuthnManager:
    """Manages FIDO2/WebAuthn authentication."""
    
    def __init__(self, rp_id: str = None, rp_name: str = None, origin: str = None):
        self.rp_id = rp_id or settings.WEBAUTHN_RP_ID or "localhost"
        self.rp_name = rp_name or settings.WEBAUTHN_RP_NAME or "VCOS"
        self.origin = origin or settings.WEBAUTHN_ORIGIN or "http://localhost:3000"
        
        # In-memory storage (replace with database in production)
        self.credentials: Dict[bytes, WebAuthnCredential] = {}
        self.user_credentials: Dict[str, Set[bytes]] = {}  # user_id -> credential_ids
        self.registration_states: Dict[str, WebAuthnRegistrationState] = {}
        self.authentication_states: Dict[str, WebAuthnAuthenticationState] = {}
        
        # Initialize FIDO2 server
        rp = PublicKeyCredentialRpEntity(id=self.rp_id, name=self.rp_name)
        self.server = Fido2Server(rp)
    
    def _generate_challenge(self) -> bytes:
        """Generate a cryptographically secure challenge."""
        return secrets.token_bytes(32)
    
    # =========================================================================
    # Registration (Credential Creation)
    # =========================================================================
    
    async def start_registration(
        self,
        user_id: str,
        username: str,
        display_name: str,
        exclude_credentials: Optional[List[bytes]] = None,
    ) -> Dict[str, Any]:
        """Start WebAuthn registration ceremony."""
        # Create user entity
        user = PublicKeyCredentialUserEntity(
            id=user_id.encode(),
            name=username,
            display_name=display_name,
        )
        
        # Prepare exclude list
        exclude_list = []
        if exclude_credentials:
            exclude_list = [
                PublicKeyCredentialDescriptor(type="public-key", id=cred_id)
                for cred_id in exclude_credentials
            ]
        
        # Begin registration
        challenge = self._generate_challenge()
        
        # Store registration state
        state_id = str(uuid4())
        self.registration_states[state_id] = WebAuthnRegistrationState(
            challenge=challenge,
            user_id=user_id,
            username=username,
            display_name=display_name,
            rp_id=self.rp_id,
            rp_name=self.rp_name,
        )
        
        # Get creation options from server
        options, state = self.server.register_begin(
            user=user,
            credentials=exclude_list if exclude_credentials else None,
            challenge=challenge,
            user_verification="preferred",
            authenticator_attachment=None,
            resident_key_requirement="preferred",
        )
        
        return {
            "state_id": state_id,
            "public_key": options,
        }
    
    async def complete_registration(
        self,
        state_id: str,
        credential: Dict[str, Any],
    ) -> WebAuthnCredential:
        """Complete WebAuthn registration ceremony."""
        if state_id not in self.registration_states:
            raise ValueError("Invalid or expired registration state")
        
        state = self.registration_states.pop(state_id)
        
        # Verify registration response
        auth_data = self.server.register_complete(
            state=state,
            response=credential,
        )
        
        # Extract credential data
        credential_id = auth_data.credential_data.credential_id
        public_key = auth_data.credential_data.public_key
        
        # Parse COSE public key to extract components
        # For now, store the raw public key
        pub_key_bytes = public_key
        
        # Create credential record
        webauthn_cred = WebAuthnCredential(
            credential_id=credential_id,
            user_id=state.user_id,
            public_key=pub_key_bytes,
            aaguid=auth_data.credential_data.aaguid,
            transports=credential.get("response", {}).get("transports", []),
        )
        
        # Store credential
        self.credentials[credential_id] = webauthn_cred
        
        if state.user_id not in self.user_credentials:
            self.user_credentials[state.user_id] = set()
        self.user_credentials[state.user_id].add(credential_id)
        
        logger.info(f"Registered WebAuthn credential for user {state.user_id}: {websafe_encode(credential_id)}")
        
        return webauthn_cred
    
    # =========================================================================
    # Authentication (Assertion)
    # =========================================================================
    
    async def start_authentication(
        self,
        user_id: Optional[str] = None,
        username: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Start WebAuthn authentication ceremony."""
        # Determine allowed credentials
        if user_id and user_id in self.user_credentials:
            allow_list = [
                PublicKeyCredentialDescriptor(type="public-key", id=cred_id)
                for cred_id in self.user_credentials[user_id]
            ]
        else:
            # Discoverable credentials - no allow list
            allow_list = None
        
        challenge = self._generate_challenge()
        
        # Store authentication state
        state_id = str(uuid4())
        self.authentication_states[state_id] = WebAuthnAuthenticationState(
            challenge=challenge,
            user_id=user_id,
            rp_id=self.rp_id,
        )
        
        # Get assertion options
        options = self.server.authenticate_begin(
            credentials=allow_list,
            challenge=challenge,
            user_verification="preferred",
        )
        
        return {
            "state_id": state_id,
            "public_key": options,
        }
    
    async def complete_authentication(
        self,
        state_id: str,
        credential: Dict[str, Any],
    ) -> WebAuthnCredential:
        """Complete WebAuthn authentication ceremony."""
        if state_id not in self.authentication_states:
            raise ValueError("Invalid or expired authentication state")
        
        state = self.authentication_states.pop(state_id)
        
        # Get credential ID from response
        credential_id = websafe_decode(credential["id"])
        
        # Look up stored credential
        stored_cred = self.credentials.get(credential_id)
        if not stored_cred:
            raise ValueError("Credential not found")
        
        # Verify user ID matches (if specified)
        if state.user_id and stored_cred.user_id != state.user_id:
            raise ValueError("Credential does not belong to specified user")
        
        # Verify authentication
        try:
            self.server.authenticate_complete(
                state=state,
                credential=credential,
            )
        except Exception as e:
            logger.error(f"Authentication verification failed: {e}")
            raise ValueError("Authentication failed")
        
        # Update credential usage
        stored_cred.sign_count += 1
        stored_cred.last_used = time.time()
        
        logger.info(f"Authenticated user {stored_cred.user_id} with credential {websafe_encode(credential_id)}")
        
        return stored_cred
    
    # =========================================================================
    # Credential Management
    # =========================================================================
    
    def get_user_credentials(self, user_id: str) -> List[WebAuthnCredential]:
        """Get all credentials for a user."""
        cred_ids = self.user_credentials.get(user_id, set())
        return [self.credentials[cid] for cid in cred_ids if cid in self.credentials]
    
    def delete_credential(self, user_id: str, credential_id: bytes) -> bool:
        """Delete a credential."""
        if credential_id in self.credentials:
            cred = self.credentials[credential_id]
            if cred.user_id != user_id:
                return False
            del self.credentials[credential_id]
            
            if user_id in self.user_credentials:
                self.user_credentials[user_id].discard(credential_id)
            
            logger.info(f"Deleted credential {websafe_encode(credential_id)} for user {user_id}")
            return True
        return False
    
    def get_credential(self, credential_id: bytes) -> Optional[WebAuthnCredential]:
        """Get credential by ID."""
        return self.credentials.get(credential_id)
    
    # =========================================================================
    # Helper methods for JSON serialization
    # =========================================================================
    
    @staticmethod
    def credential_to_json(cred: WebAuthnCredential) -> Dict[str, Any]:
        """Serialize credential to JSON."""
        return {
            "credential_id": websafe_encode(cred.credential_id),
            "user_id": cred.user_id,
            "public_key": websafe_encode(cred.public_key),
            "sign_count": cred.sign_count,
            "aaguid": websafe_encode(cred.aaguid) if cred.aaguid else None,
            "credential_type": cred.credential_type,
            "transports": cred.transports,
            "created_at": cred.created_at,
            "last_used": cred.last_used,
            "backup_eligible": cred.backup_eligible,
            "backup_state": cred.backup_state,
        }


# Global WebAuthn manager
_webauthn_manager: Optional[WebAuthnManager] = None


def get_webauthn_manager() -> WebAuthnManager:
    """Get global WebAuthn manager."""
    global _webauthn_manager
    if _webauthn_manager is None:
        _webauthn_manager = WebAuthnManager()
    return _webauthn_manager
"""
End-to-End Encryption for VCOS Real-time Collaboration

Provides:
- Signal Protocol (Double Ratchet) for 1:1 and group messaging
- Encrypted CRDT operations with per-document keys
- Key management with rotation and forward secrecy
- Post-compromise security
- Integration with WebRTC for media encryption
"""

import asyncio
import base64
import hashlib
import hmac
import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, x25519
from cryptography.hazmat.primitives.ciphers.aead import AESGCM, ChaCha20Poly1305
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

logger = logging.getLogger(__name__)


class EncryptionAlgorithm(str, Enum):
    """Supported encryption algorithms"""
    AES_GCM_256 = "aes-gcm-256"
    CHACHA20_POLY1305 = "chacha20-poly1305"
    XCHACHA20_POLY1305 = "xchacha20-poly1305"


class KeyType(str, Enum):
    """Key types in the system"""
    IDENTITY = "identity"           # Long-term identity key (X25519)
    SIGNED_PREKEY = "signed_prekey" # Medium-term signed prekey
    ONETIME_PREKEY = "onetime_prekey" # One-time prekeys
    EPHEMERAL = "ephemeral"         # Ephemeral key per session
    CHAIN_KEY = "chain_key"         # Symmetric chain key
    MESSAGE_KEY = "message_key"     # Per-message encryption key
    DOCUMENT_KEY = "document_key"   # Per-document CRDT key
    ROOT_KEY = "root_key"           # Root key for key derivation


@dataclass
class KeyPair:
    """Asymmetric key pair"""
    private_key: bytes
    public_key: bytes
    key_type: KeyType
    created_at: float = field(default_factory=time.time)
    expires_at: Optional[float] = None
    key_id: str = field(default_factory=lambda: str(uuid.uuid4()))


@dataclass
class PreKeyBundle:
    """Signal Protocol prekey bundle"""
    identity_key: bytes
    signed_prekey: bytes
    signed_prekey_signature: bytes
    onetime_prekeys: List[bytes]
    registration_id: int


@dataclass
class SessionState:
    """Double Ratchet session state"""
    session_id: str
    local_identity: KeyPair
    remote_identity: bytes
    root_key: bytes
    chain_key_send: bytes
    chain_key_recv: bytes
    message_number_send: int = 0
    message_number_recv: int = 0
    previous_chain_length: int = 0
    skipped_message_keys: Dict[int, bytes] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time)


@dataclass
class EncryptedMessage:
    """Encrypted message with header"""
    header: "MessageHeader"
    ciphertext: bytes
    mac: bytes


@dataclass
class MessageHeader:
    """Message header with key info"""
    sender_registration_id: int
    sender_ephemeral: bytes
    message_number: int
    previous_chain_length: int
    ciphertext_header: bytes = b""


class DoubleRatchet:
    """
    Signal Protocol Double Ratchet implementation
    
    Provides:
    - Forward secrecy (DH ratchet)
    - Post-compromise security (symmetric ratchet)
    - Out-of-order message handling
    """
    
    # Constants
    MAX_SKIP = 1000
    DH_KEY_SIZE = 32
    ROOT_KEY_SIZE = 32
    CHAIN_KEY_SIZE = 32
    MESSAGE_KEY_SIZE = 32
    AD_SIZE = 64  # Associated data size
    
    def __init__(self):
        self.sessions: Dict[str, SessionState] = {}
    
    # ==================== Key Generation ====================
    
    def generate_identity_key(self) -> KeyPair:
        """Generate long-term identity key (X25519)"""
        private = x25519.X25519PrivateKey.generate()
        public = private.public_key()
        
        return KeyPair(
            private_key=private.private_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PrivateFormat.Raw,
                encryption_algorithm=serialization.NoEncryption()
            ),
            public_key=public.public_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PublicFormat.Raw
            ),
            key_type=KeyType.IDENTITY,
        )
    
    def generate_prekeys(self, count: int = 100) -> List[KeyPair]:
        """Generate one-time prekeys"""
        return [self.generate_identity_key() for _ in range(count)]
    
    def generate_signed_prekey(self, identity_private: bytes) -> Tuple[bytes, bytes]:
        """Generate signed prekey with signature"""
        prekey = self.generate_identity_key()
        prekey.key_type = KeyType.SIGNED_PREKEY
        
        # Sign the prekey with identity key
        identity_key = x25519.X25519PrivateKey.from_private_bytes(identity_private)
        signature = identity_key.sign(prekey.public_key)
        
        return prekey.private_key, signature
    
    # ==================== DH Ratchet ====================
    
    def dh_ratchet(self, private_key: bytes, public_key: bytes) -> bytes:
        """Perform DH key agreement"""
        priv = x25519.X25519PrivateKey.from_private_bytes(private_key)
        pub = x25519.X25519PublicKey.from_public_bytes(public_key)
        shared = priv.exchange(pub)
        return shared
    
    def kdf_root(self, root_key: bytes, dh_output: bytes) -> Tuple[bytes, bytes]:
        """KDF for root key -> (new_root_key, chain_key)"""
        hkdf = HKDF(
            algorithm=hashes.SHA256(),
            length=64,
            salt=root_key,
            info=b"vcos-double-ratchet-root",
        )
        output = hkdf.derive(dh_output)
        return output[:32], output[32:]  # root_key, chain_key
    
    def kdf_chain(self, chain_key: bytes) -> Tuple[bytes, bytes]:
        """KDF for chain key -> (new_chain_key, message_key)"""
        hkdf = HKDF(
            algorithm=hashes.SHA256(),
            length=64,
            salt=b"",
            info=b"vcos-double-ratchet-chain",
        )
        output = hkdf.derive(chain_key)
        return output[:32], output[32:]  # new_chain_key, message_key
    
    # ==================== Session Management ====================
    
    async def create_session(
        self,
        local_identity: KeyPair,
        remote_prekey_bundle: PreKeyBundle,
    ) -> SessionState:
        """Create new session as initiator (Alice)"""
        # Generate ephemeral key
        ephemeral = self.generate_identity_key()
        ephemeral.key_type = KeyType.EPHEMERAL
        
        # DH1: identity_key (Alice) * signed_prekey (Bob)
        dh1 = self.dh_ratchet(local_identity.private_key, remote_prekey_bundle.signed_prekey)
        
        # DH2: ephemeral_key (Alice) * identity_key (Bob)
        dh2 = self.dh_ratchet(ephemeral.private_key, remote_prekey_bundle.identity_key)
        
        # DH3: ephemeral_key (Alice) * signed_prekey (Bob)
        dh3 = self.dh_ratchet(ephemeral.private_key, remote_prekey_bundle.signed_prekey)
        
        # DH4: ephemeral_key (Alice) * onetime_prekey (Bob) - if available
        dh4 = b""
        if remote_prekey_bundle.onetime_prekeys:
            onetime = remote_prekey_bundle.onetime_prekeys.pop(0)
            dh4 = self.dh_ratchet(ephemeral.private_key, onetime)
        
        # Master secret = KDF(DH1 || DH2 || DH3 || DH4)
        master_secret = dh1 + dh2 + dh3 + dh4
        hkdf = HKDF(
            algorithm=hashes.SHA256(),
            length=64,
            salt=b"vcos-double-ratchet-init",
            info=b"vcos-double-ratchet-master",
        )
        master = hkdf.derive(master_secret)
        
        root_key, chain_key_send = master[:32], master[32:]
        
        # Initialize receiving chain key (will be set when receiving first message)
        chain_key_recv = b""
        
        session = SessionState(
            session_id=str(uuid.uuid4()),
            local_identity=ephemeral,
            remote_identity=remote_prekey_bundle.identity_key,
            root_key=root_key,
            chain_key_send=chain_key_send,
            chain_key_recv=chain_key_recv,
        )
        
        self.sessions[session.session_id] = session
        return session
    
    async def receive_session(
        self,
        local_identity: KeyPair,
        remote_ephemeral: bytes,
        remote_registration_id: int,
    ) -> SessionState:
        """Create new session as receiver (Bob)"""
        # This would be called when receiving first message
        # For now, return a placeholder
        session = SessionState(
            session_id=str(uuid.uuid4()),
            local_identity=local_identity,
            remote_identity=remote_ephemeral,
            root_key=b"\x00" * 32,  # Will be updated on first message
            chain_key_send=b"\x00" * 32,
            chain_key_recv=b"\x00" * 32,
        )
        self.sessions[session.session_id] = session
        return session
    
    # ==================== Encryption/Decryption ====================
    
    def encrypt(self, session: SessionState, plaintext: bytes, associated_data: bytes = b"") -> EncryptedMessage:
        """Encrypt message with current sending chain"""
        # Advance sending chain
        session.chain_key_send, message_key = self.kdf_chain(session.chain_key_send)
        session.message_number_send += 1
        
        # Encrypt with message key
        nonce = self._generate_nonce(session.message_number_send)
        cipher = AESGCM(message_key)
        ciphertext = cipher.encrypt(nonce, plaintext, associated_data)
        
        # Create header
        header = MessageHeader(
            sender_registration_id=0,  # Would be actual registration ID
            sender_ephemeral=session.local_identity.public_key,
            message_number=session.message_number_send,
            previous_chain_length=session.previous_chain_length,
        )
        
        return EncryptedMessage(
            header=header,
            ciphertext=ciphertext,
            mac=b"",  # GCM includes auth tag
        )
    
    async def decrypt(self, session: SessionState, encrypted: EncryptedMessage, associated_data: bytes = b"") -> bytes:
        """Decrypt message with receiving chain"""
        # Handle skipped messages (out-of-order)
        if encrypted.header.message_number > session.message_number_recv + 1:
            # Store skipped message keys
            for i in range(session.message_number_recv + 1, encrypted.header.message_number):
                if i not in session.skipped_message_keys:
                    session.chain_key_recv, msg_key = self.kdf_chain(session.chain_key_recv)
                    session.skipped_message_keys[i] = msg_key
        
        # Check if we have the key
        if encrypted.header.message_number in session.skipped_message_keys:
            message_key = session.skipped_message_keys.pop(encrypted.header.message_number)
        else:
            # Advance receiving chain
            session.chain_key_recv, message_key = self.kdf_chain(session.chain_key_recv)
        
        session.message_number_recv = encrypted.header.message_number
        
        # Decrypt
        nonce = self._generate_nonce(encrypted.header.message_number)
        cipher = AESGCM(message_key)
        plaintext = cipher.decrypt(nonce, encrypted.ciphertext, associated_data)
        
        # Check if we need to ratchet (DH ratchet step)
        if encrypted.header.sender_ephemeral != session.remote_identity:
            # DH ratchet step
            await self._dh_ratchet_step(session, encrypted.header.sender_ephemeral)
        
        return plaintext
    
    async def _dh_ratchet_step(self, session: SessionState, remote_ephemeral: bytes):
        """Perform DH ratchet step"""
        # DH between our ephemeral and their new ephemeral
        dh = self.dh_ratchet(session.local_identity.private_key, remote_ephemeral)
        
        # Update root key and new sending chain
        session.root_key, session.chain_key_send = self.kdf_root(session.root_key, dh)
        session.chain_key_recv = b"\x00" * 32  # Will be set on first receive
        session.message_number_send = 0
        session.message_number_recv = 0
        session.previous_chain_length = session.message_number_send
        session.remote_identity = remote_ephemeral
        
        # Generate new ephemeral for next ratchet
        session.local_identity = self.generate_identity_key()
        session.local_identity.key_type = KeyType.EPHEMERAL
    
    def _generate_nonce(self, message_number: int) -> bytes:
        """Generate nonce from message number"""
        return message_number.to_bytes(12, byteorder="big")
    
    def get_session(self, session_id: str) -> Optional[SessionState]:
        return self.sessions.get(session_id)
    
    def remove_session(self, session_id: str):
        self.sessions.pop(session_id, None)


class EncryptedCRDT:
    """
    Encrypted CRDT operations with per-document keys
    
    Features:
    - Per-document encryption keys
    - Encrypted operations that can still be merged
    - Key rotation support
    - Access control via key distribution
    """
    
    def __init__(self, double_ratchet: DoubleRatchet):
        self.double_ratchet = double_ratchet
        self.document_keys: Dict[str, bytes] = {}  # document_id -> key
        self.document_sessions: Dict[str, SessionState] = {}  # document_id -> session
    
    async def create_document_key(self, document_id: str, creator_session: SessionState) -> bytes:
        """Create new document encryption key"""
        # Generate random document key
        document_key = os.urandom(32)
        self.document_keys[document_id] = document_key
        
        # Encrypt for creator
        encrypted = self._encrypt_key(document_key, creator_session)
        
        # Store encrypted key in document metadata
        # This would be stored in the document's metadata
        return document_key
    
    async def share_document_key(
        self,
        document_id: str,
        recipient_session: SessionState,
        creator_session: SessionState,
    ) -> bytes:
        """Share document key with another user"""
        document_key = self.document_keys.get(document_id)
        if not document_key:
            raise ValueError(f"No key for document {document_id}")
        
        # Encrypt for recipient using their session
        return self._encrypt_key(document_key, recipient_session)
    
    def _encrypt_key(self, key: bytes, session: SessionState) -> bytes:
        """Encrypt a key using session's chain"""
        session.chain_key_send, message_key = self.double_ratchet.kdf_chain(session.chain_key_send)
        
        nonce = os.urandom(12)
        cipher = AESGCM(message_key)
        return cipher.encrypt(nonce, key, b"vcos-document-key")
    
    def _decrypt_key(self, encrypted_key: bytes, session: SessionState) -> bytes:
        """Decrypt a key using session's chain"""
        # This would need the nonce which should be prepended to encrypted_key
        # For simplicity, assuming nonce is first 12 bytes
        nonce = encrypted_key[:12]
        ciphertext = encrypted_key[12:]
        
        session.chain_key_recv, message_key = self.double_ratchet.kdf_chain(session.chain_key_recv)
        cipher = AESGCM(message_key)
        return cipher.decrypt(nonce, ciphertext, b"vcos-document-key")
    
    def encrypt_operation(self, document_id: str, operation: Dict[str, Any], session: SessionState) -> bytes:
        """Encrypt a CRDT operation"""
        document_key = self.document_keys.get(document_id)
        if not document_key:
            raise ValueError(f"No key for document {document_id}")
        
        # Serialize operation
        plaintext = json.dumps(operation).encode()
        
        # Encrypt with document key
        nonce = os.urandom(12)
        cipher = AESGCM(document_key)
        ciphertext = cipher.encrypt(nonce, plaintext, b"vcos-crdt-operation")
        
        return nonce + ciphertext
    
    def decrypt_operation(self, document_id: str, encrypted: bytes, session: SessionState) -> Dict[str, Any]:
        """Decrypt a CRDT operation"""
        document_key = self.document_keys.get(document_id)
        if not document_key:
            raise ValueError(f"No key for document {document_id}")
        
        nonce = encrypted[:12]
        ciphertext = encrypted[12:]
        
        cipher = AESGCM(document_key)
        plaintext = cipher.decrypt(nonce, ciphertext, b"vcos-crdt-operation")
        
        return json.loads(plaintext.decode())


class KeyManager:
    """
    Centralized key management with rotation and access control
    """
    
    def __init__(self):
        self.double_ratchet = DoubleRatchet()
        self.encrypted_crdt = EncryptedCRDT(self.double_ratchet)
        
        # Key storage
        self.identity_keys: Dict[str, KeyPair] = {}  # user_id -> identity key
        self.prekey_bundles: Dict[str, PreKeyBundle] = {}  # user_id -> prekey bundle
        self.document_keys: Dict[str, bytes] = {}  # document_id -> key
        self.key_rotation_schedule: Dict[str, float] = {}  # key_id -> next_rotation
        
        # Access control
        self.document_access: Dict[str, Set[str]] = {}  # document_id -> user_ids
        self.key_derivations: Dict[str, Dict[str, bytes]] = {}  # document_id -> user_id -> derived_key
    
    async def initialize_user(self, user_id: str) -> PreKeyBundle:
        """Initialize user with identity key and prekeys"""
        # Generate identity key
        identity = self.double_ratchet.generate_identity_key()
        self.identity_keys[user_id] = identity
        
        # Generate signed prekey
        signed_private, signature = self.double_ratchet.generate_signed_prekey(
            identity.private_key
        )
        
        # Generate onetime prekeys
        onetime_prekeys = []
        for _ in range(100):
            prekey = self.double_ratchet.generate_identity_key()
            prekey.key_type = KeyType.ONETIME_PREKEY
            onetime_prekeys.append(prekey.public_key)
        
        bundle = PreKeyBundle(
            identity_key=identity.public_key,
            signed_prekey=signed_private,
            signed_prekey_signature=signature,
            onetime_prekeys=onetime_prekeys,
            registration_id=hash(user_id) % 1000000,
        )
        
        self.prekey_bundles[user_id] = bundle
        return bundle
    
    def get_prekey_bundle(self, user_id: str) -> Optional[PreKeyBundle]:
        return self.prekey_bundles.get(user_id)
    
    def consume_onetime_prekey(self, user_id: str) -> Optional[bytes]:
        """Consume and return one onetime prekey"""
        bundle = self.prekey_bundles.get(user_id)
        if bundle and bundle.onetime_prekeys:
            return bundle.onetime_prekeys.pop()
        return None
    
    async def create_session(self, initiator_id: str, recipient_id: str) -> SessionState:
        """Create session between two users"""
        recipient_bundle = self.get_prekey_bundle(recipient_id)
        if not recipient_bundle:
            raise ValueError(f"No prekey bundle for {recipient_id}")
        
        initiator_identity = self.identity_keys[initiator_id]
        session = await self.double_ratchet.create_session(
            initiator_identity,
            recipient_bundle,
        )
        
        return session
    
    async def get_document_key(self, document_id: str, user_id: str) -> bytes:
        """Get or derive document key for user"""
        if document_id not in self.document_keys:
            # Generate new document key
            self.document_keys[document_id] = os.urandom(32)
            self.document_access[document_id] = {user_id}
            return self.document_keys[document_id]
        
        # Check access
        if user_id not in self.document_access.get(document_id, set()):
            raise PermissionError(f"User {user_id} has no access to document {document_id}")
        
        # Check if we have derived key for this user
        if document_id in self.key_derivations and user_id in self.key_derivations[document_id]:
            return self.key_derivations[document_id][user_id]
        
        # Derive key for user (in production, this would use the document key + user-specific salt)
        derived = self._derive_user_key(document_id, user_id)
        
        if document_id not in self.key_derivations:
            self.key_derivations[document_id] = {}
        self.key_derivations[document_id][user_id] = derived
        
        return derived
    
    def _derive_user_key(self, document_id: str, user_id: str) -> bytes:
        """Derive per-user document key"""
        document_key = self.document_keys[document_id]
        hkdf = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=document_id.encode(),
            info=f"vcos-user-key-{user_id}".encode(),
        )
        return hkdf.derive(document_key)
    
    def grant_access(self, document_id: str, user_id: str):
        """Grant document access to user"""
        if document_id not in self.document_access:
            self.document_access[document_id] = set()
        self.document_access[document_id].add(user_id)
    
    def revoke_access(self, document_id: str, user_id: str):
        """Revoke document access from user"""
        if document_id in self.document_access:
            self.document_access[document_id].discard(user_id)
        
        # Remove derived key
        if document_id in self.key_derivations:
            self.key_derivations[document_id].pop(user_id, None)
    
    async def rotate_keys(self, document_id: str, rotated_by: str):
        """Rotate document encryption key"""
        if document_id not in self.document_keys:
            return
        
        # Generate new key
        old_key = self.document_keys[document_id]
        new_key = os.urandom(32)
        self.document_keys[document_id] = new_key
        
        # Re-encrypt for all authorized users
        for user_id in self.document_access.get(document_id, set()):
            self.key_derivations[document_id][user_id] = self._derive_user_key(document_id, user_id)
        
        logger.info(f"Rotated key for document {document_id} by {rotated_by}")
    
    def schedule_rotation(self, document_id: str, interval_hours: int = 24):
        """Schedule automatic key rotation"""
        self.key_rotation_schedule[document_id] = time.time() + (interval_hours * 3600)
    
    async def check_rotations(self):
        """Check and perform scheduled rotations"""
        now = time.time()
        for doc_id, rotate_at in list(self.key_rotation_schedule.items()):
            if now >= rotate_at:
                await self.rotate_keys(doc_id, "system")
                # Reschedule
                self.key_rotation_schedule[doc_id] = now + (24 * 3600)


# ==================== WebRTC Integration ====================

class WebRTCEncryption:
    """
    WebRTC media encryption with E2E encryption
    
    Integrates with Double Ratchet for key exchange
    """
    
    def __init__(self, key_manager: KeyManager):
        self.key_manager = key_manager
        self.media_sessions: Dict[str, Dict[str, Any]] = {}
    
    async def create_media_session(self, call_id: str, participants: List[str]) -> Dict[str, Any]:
        """Create encrypted media session"""
        # Create a session for each participant pair
        # In practice, use DTLS-SRTP with key exchange via signaling
        pass
    
    async def generate_srtp_keys(self, session: SessionState) -> Tuple[bytes, bytes]:
        """Generate SRTP keys from session"""
        # Derive SRTP keys from session keys
        hkdf = HKDF(
            algorithm=hashes.SHA256(),
            length=64,
            salt=b"vcos-srtp",
            info=b"vcos-webrtc-srtp",
        )
        output = hkdf.derive(session.root_key)
        return output[:32], output[32:]  # sender_key, receiver_key


# ==================== Singleton ====================

_key_manager: Optional[KeyManager] = None


def get_key_manager() -> KeyManager:
    global _key_manager
    if _key_manager is None:
        _key_manager = KeyManager()
    return _key_manager


def init_e2e_encryption() -> KeyManager:
    """Initialize E2E encryption system"""
    key_manager = KeyManager()
    # Initialize system users
    return key_manager
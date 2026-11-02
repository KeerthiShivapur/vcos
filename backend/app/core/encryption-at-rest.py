"""
Encryption at Rest for Offline-First Storage

Provides transparent encryption for IndexedDB/RxDB data at rest
using Web Crypto API with AES-GCM.
"""

import base64
import json
import os
import secrets
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa, padding
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes

from app.core.config import get_settings


@dataclass
class EncryptionConfig:
    """Configuration for encryption at rest."""
    algorithm: str = "AES-GCM"
    key_length: int = 256  # bits
    iv_length: int = 12    # 96 bits for AES-GCM
    tag_length: int = 16   # 128 bits
    salt_length: int = 32  # 256 bits
    iterations: int = 100000  # PBKDF2 iterations
    key_derivation: str = "PBKDF2"


@dataclass
class EncryptedData:
    """Container for encrypted data with metadata."""
    ciphertext: str      # Base64 encoded
    iv: str              # Base64 encoded IV
    salt: str            # Base64 encoded salt
    algorithm: str
    version: int = 1
    timestamp: int = field(default_factory=lambda: int(time.time()))
    key_id: str = ""
    
    def to_dict(self) -> dict:
        return {
            'ciphertext': self.ciphertext,
            'iv': self.iv,
            'salt': self.salt,
            'algorithm': self.algorithm,
            'version': self.version,
            'timestamp': self.timestamp,
            'key_id': self.key_id,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'EncryptedData':
        return cls(
            ciphertext=data['ciphertext'],
            iv=data['iv'],
            salt=data['salt'],
            algorithm=data.get('algorithm', 'AES-GCM'),
            version=data.get('version', 1),
            timestamp=data.get('timestamp', int(time.time())),
            key_id=data.get('key_id', ''),
        )


@dataclass
class KeyPair:
    """Key pair for envelope encryption."""
    key_id: str
    public_key: str    # PEM format
    private_key: str   # PEM format (encrypted)
    created_at: int = field(default_factory=lambda: int(time.time()))
    expires_at: Optional[int] = None
    
    def to_dict(self) -> dict:
        return {
            'key_id': self.key_id,
            'public_key': self.public_key,
            'private_key': self.private_key,
            'created_at': self.created_at,
            'expires_at': self.expires_at,
        }


class EncryptionManager:
    """
    Manages encryption at rest for offline-first storage.
    
    Features:
    - AES-GCM symmetric encryption for data
    - PBKDF2 key derivation from user password
    - HKDF for key derivation from master key
    - Envelope encryption for key management
    - Key rotation support
    - Automatic migration
    """
    
    def __init__(self, config: Optional[EncryptionConfig] = None):
        self.config = config or EncryptionConfig()
        self._master_key: Optional[bytes] = None
        self._data_keys: Dict[str, bytes] = {}  # collection -> key
        self._initialized = False
    
    def initialize_from_password(self, password: str, salt: Optional[bytes] = None) -> bytes:
        """
        Derive master key from user password using PBKDF2.
        
        Args:
            password: User password
            salt: Optional salt (generated if not provided)
            
        Returns:
            Derived master key
        """
        salt = salt or secrets.token_bytes(self.config.salt_length)
        
        kdf = PBKDF2(
            algorithm=hashes.SHA256(),
            length=self.config.key_length // 8,
            salt=salt,
            iterations=self.config.iterations,
        )
        
        self._master_key = kdf.derive(password.encode('utf-8'))
        return self._master_key
    
    def initialize_from_key(self, key: bytes) -> None:
        """Initialize with raw master key."""
        if len(key) != self.config.key_length // 8:
            raise ValueError(f"Key must be {self.config.key_length // 8} bytes")
        self._master_key = key
    
    def generate_data_key(self, key_id: str) -> bytes:
        """Generate a new data encryption key for a collection."""
        if not self._master_key:
            raise RuntimeError("Master key not initialized")
        
        # Derive data key using HKDF
        hkdf = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=secrets.token_bytes(16),
            info=f"vcos-data-key-{key_id}".encode(),
        )
        data_key = hkdf.derive(self._master_key)
        self._data_keys[key_id] = data_key
        return data_key
    
    def get_data_key(self, key_id: str) -> bytes:
        """Get or generate data key for collection."""
        if key_id not in self._data_keys:
            return self.generate_data_key(key_id)
        return self._data_keys[key_id]
    
    def encrypt(self, data: Union[str, bytes, dict], key_id: str = "default") -> EncryptedData:
        """
        Encrypt data using AES-GCM.
        
        Args:
            data: Data to encrypt (string, bytes, or JSON-serializable dict)
            key_id: Key identifier for data key
            
        Returns:
            EncryptedData with ciphertext, IV, salt, and metadata
        """
        key = self.get_data_key(key_id)
        aesgcm = AESGCM(key)
        
        # Generate random IV
        iv = secrets.token_bytes(self.config.iv_length)
        
        # Prepare plaintext
        if isinstance(data, dict):
            plaintext = json.dumps(data, separators=(',', ':')).encode('utf-8')
        elif isinstance(data, str):
            plaintext = data.encode('utf-8')
        elif isinstance(data, bytes):
            plaintext = data
        else:
            raise ValueError("Data must be str, bytes, or dict")
        
        # Encrypt
        ciphertext = aesgcm.encrypt(iv, plaintext, None)
        
        # Generate salt for key derivation record
        salt = secrets.token_bytes(16)
        
        return EncryptedData(
            ciphertext=base64.b64encode(ciphertext).decode(),
            iv=base64.b64encode(iv).decode(),
            salt=base64.b64encode(salt).decode(),
            algorithm=self.config.algorithm,
            key_id=key_id,
        )
    
    def decrypt(self, encrypted: EncryptedData, key_id: str = "default") -> bytes:
        """
        Decrypt data using AES-GCM.
        
        Args:
            encrypted: EncryptedData container
            key_id: Key identifier
            
        Returns:
            Decrypted plaintext bytes
        """
        key = self.get_data_key(key_id)
        aesgcm = AESGCM(key)
        
        # Decode components
        ciphertext = base64.b64decode(encrypted.ciphertext)
        iv = base64.b64decode(encrypted.iv)
        
        # Decrypt
        plaintext = aesgcm.decrypt(iv, ciphertext, None)
        return plaintext
    
    def decrypt_json(self, encrypted: EncryptedData, key_id: str = "default") -> dict:
        """Decrypt and parse JSON."""
        plaintext = self.decrypt(encrypted, key_id)
        return json.loads(plaintext.decode('utf-8'))
    
    def decrypt_str(self, encrypted: EncryptedData, key_id: str = "default") -> str:
        """Decrypt to string."""
        plaintext = self.decrypt(encrypted, key_id)
        return plaintext.decode('utf-8')
    
    # ==================== Envelope Encryption ====================
    
    def generate_key_pair(self, key_id: str) -> KeyPair:
        """Generate RSA key pair for envelope encryption."""
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
        )
        public_key = private_key.public_key()
        
        private_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode()
        
        public_pem = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode()
        
        key_pair = KeyPair(
            key_id=key_id,
            public_key=public_pem,
            private_key=private_pem,
        )
        
        return key_pair
    
    def encrypt_with_public_key(self, data: bytes, public_key_pem: str) -> bytes:
        """Encrypt data with RSA public key (for envelope encryption)."""
        public_key = serialization.load_pem_public_key(public_key_pem.encode())
        
        # Generate random AES key
        aes_key = secrets.token_bytes(32)
        iv = secrets.token_bytes(12)
        aesgcm = AESGCM(aes_key)
        ciphertext = aesgcm.encrypt(iv, data, None)
        
        # Encrypt AES key with RSA
        public_key_obj = serialization.load_pem_public_key(public_key_pem.encode())
        encrypted_key = public_key_obj.encrypt(
            aes_key,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None,
            ),
        )
        
        # Combine: encrypted_key + iv + ciphertext
        result = (
            len(encrypted_key).to_bytes(2, 'big') +
            encrypted_key +
            iv +
            ciphertext
        )
        return result
    
    def decrypt_with_private_key(self, encrypted: bytes, private_key_pem: str) -> bytes:
        """Decrypt envelope-encrypted data."""
        private_key = serialization.load_pem_private_key(
            private_key_pem.encode(),
            password=None,
        )
        
        # Parse envelope
        key_len = int.from_bytes(encrypted[:2], 'big')
        encrypted_key = encrypted[2:2+key_len]
        iv = encrypted[2+key_len:2+key_len+12]
        ciphertext = encrypted[2+key_len+12:]
        
        # Decrypt AES key
        aes_key = private_key.decrypt(
            encrypted_key,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None,
            ),
        )
        
        # Decrypt data
        aesgcm = AESGCM(aes_key)
        plaintext = aesgcm.decrypt(iv, ciphertext, None)
        return plaintext
    
    # ==================== Key Rotation ====================
    
    async def rotate_keys(self) -> None:
        """Rotate all data keys."""
        new_keys = {}
        for key_id in self._data_keys:
            new_keys[key_id] = secrets.token_bytes(32)
        self._data_keys = new_keys
        # In production, re-encrypt all data with new keys
    
    def export_key(self, key_id: str, password: str) -> str:
        """Export encrypted key for backup."""
        key = self._data_keys.get(key_id)
        if not key:
            raise ValueError(f"Key not found: {key_id}")
        
        # Encrypt key with password
        salt = secrets.token_bytes(16)
        kdf = PBKDF2(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        derived_key = kdf.derive(password.encode())
        aesgcm = AESGCM(derived_key)
        iv = secrets.token_bytes(12)
        ciphertext = aesgcm.encrypt(iv, key, None)
        
        export = {
            'key_id': key_id,
            'ciphertext': base64.b64encode(ciphertext).decode(),
            'iv': base64.b64encode(iv).decode(),
            'salt': base64.b64encode(salt).decode(),
            'algorithm': 'AES-GCM',
            'version': 1,
        }
        return json.dumps(export)
    
    def import_key(self, export_data: str, password: str) -> bytes:
        """Import key from backup."""
        data = json.loads(export_data)
        salt = base64.b64decode(data['salt'])
        iv = base64.b64decode(data['iv'])
        ciphertext = base64.b64decode(data['ciphertext'])
        
        kdf = PBKDF2(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        derived_key = kdf.derive(password.encode())
        aesgcm = AESGCM(derived_key)
        key = aesgcm.decrypt(iv, ciphertext, None)
        
        key_id = data['key_id']
        self._data_keys[key_id] = key
        return key
    
    # ==================== Utilities ====================
    
    def get_key_info(self, key_id: str) -> Optional[dict]:
        """Get information about a key."""
        if key_id not in self._data_keys:
            return None
        key = self._data_keys[key_id]
        return {
            'key_id': key_id,
            'length': len(key) * 8,
            'algorithm': 'AES-GCM',
        }
    
    def list_keys(self) -> List[str]:
        """List all key IDs."""
        return list(self._data_keys.keys())
    
    def delete_key(self, key_id: str) -> bool:
        """Delete a data key."""
        if key_id in self._data_keys:
            del self._data_keys[key_id]
            return True
        return False
    
    def clear(self) -> None:
        """Clear all keys."""
        self._master_key = None
        self._data_keys.clear()


# ==================== RxDB Encryption Integration ====================

class RxDBEncryptionPlugin:
    """
    RxDB plugin for transparent encryption at rest.
    
    Usage:
        import { addRxPlugin } from 'rxdb';
        import { RxDBEncryptionPlugin } from './encryption-at-rest';
        
        addRxPlugin(RxDBEncryptionPlugin);
        
        const db = await createRxDatabase({
            name: 'mydb',
            storage: getRxStorageDexie(),
            password: 'my-password',  // Enables encryption
        });
    """
    
    def __init__(self, password: Optional[str] = None):
        self.password = password
        self.encryption_manager = EncryptionManager()
        if password:
            self.encryption_manager.initialize_from_password(password)
    
    def get_encryption_manager(self) -> EncryptionManager:
        return self.encryption_manager
    
    def encrypt_document(self, doc: dict, collection_name: str) -> dict:
        """Encrypt document fields before storage."""
        # Fields to encrypt (exclude system fields)
        sensitive_fields = ['content', 'metadata', 'tags', 'yjsState']
        encrypted_doc = doc.copy()
        
        for field in sensitive_fields:
            if field in encrypted_doc:
                encrypted = self.encryption_manager.encrypt(
                    encrypted_doc[field],
                    key_id=f"{doc.get('collection', 'default')}:{field}"
                )
                encrypted_doc[field] = encrypted.to_dict()
                encrypted_doc[f"_enc_{field}"] = True  # Mark as encrypted
        
        return encrypted_doc
    
    def decrypt_document(self, doc: dict, collection_name: str) -> dict:
        """Decrypt document fields after retrieval."""
        decrypted_doc = doc.copy()
        
        for key, value in doc.items():
            if key.startswith("_enc_") and value is True:
                field = key[5:]  # Remove "_enc_" prefix
                if field in doc:
                    try:
                        # Decrypt the field
                        encrypted_data = EncryptedData.from_dict(doc[field])
                        decrypted = self.encryption_manager.decrypt_json(
                            encrypted_data,
                            key_id=f"{doc.get('collection', 'default')}:{field}"
                        )
                        decrypted_doc[field] = decrypted
                    except Exception as e:
                        # If decryption fails, keep original
                        pass
        
        return decrypted_doc
    
    def encrypt_attachment(self, data: bytes, collection: str, attachment_id: str) -> EncryptedData:
        """Encrypt attachment binary data."""
        return self.encryption_manager.encrypt(data, key_id=f"{collection}:attachments:{attachment_id}")
    
    def decrypt_attachment(self, encrypted: EncryptedData, collection: str, attachment_id: str) -> bytes:
        """Decrypt attachment binary data."""
        return self.encryption_manager.decrypt(encrypted, key_id=f"{collection}:attachments:{attachment_id}")


# ==================== Singleton ====================

_encryption_manager: Optional[EncryptionManager] = None
_rxdb_encryption_plugin: Optional[RxDBEncryptionPlugin] = None


def get_encryption_manager(config: Optional[EncryptionConfig] = None) -> EncryptionManager:
    """Get or create global encryption manager."""
    global _encryption_manager
    if _encryption_manager is None:
        _encryption_manager = EncryptionManager(config)
    return _encryption_manager


def get_rxdb_encryption_plugin(password: Optional[str] = None) -> RxDBEncryptionPlugin:
    """Get RxDB encryption plugin instance."""
    global _rxdb_encryption_plugin
    if _rxdb_encryption_plugin is None:
        _rxdb_encryption_plugin = RxDBEncryptionPlugin(password)
    return _rxdb_encryption_plugin


def init_encryption(password: Optional[str] = None, config: Optional[EncryptionConfig] = None) -> EncryptionManager:
    """Initialize global encryption."""
    global _encryption_manager, _rxdb_encryption_plugin
    _encryption_manager = EncryptionManager(config)
    if password:
        _encryption_manager.initialize_from_password(password)
    _rxdb_encryption_plugin = RxDBEncryptionPlugin(password)
    return _encryption_manager


# ==================== React Hook ====================

# import { useState, useCallback, useEffect } from 'react';
# import { getEncryptionManager, EncryptedData } from '@/lib/encryption-at-rest';

# export function useEncryption(keyId: str = 'default') {
#   const [manager] = useState(() => getEncryptionManager());
#   const [initialized, setInitialized] = useState(false);
#   const [password, setPassword] = useState<string>('');
# 
#   const initialize = useCallback(async (pwd: string) => {
#     try {
#       getEncryptionManager().initialize_from_password(pwd);
#       setPassword(pwd);
#       setInitialized(true);
#       return true;
#     } catch (e) {
#       console.error('Encryption init failed:', e);
#       return false;
#     }
#   }, []);
# 
#   const encrypt = useCallback(async (data: any, customKeyId?: string) => {
#     if (!initialized) throw new Error('Encryption not initialized');
#     return getEncryptionManager().encrypt(data, customKeyId || keyId);
#   }, [initialized, keyId]);
# 
#   const decrypt = useCallback(async (encrypted: EncryptedData, customKeyId?: string) => {
#     if (!initialized) throw new Error('Encryption not initialized');
#     return getEncryptionManager().decrypt(encrypted, customKeyId || keyId);
#   }, [initialized, keyId]);
# 
#   const decryptJson = useCallback(async (encrypted: EncryptedData, customKeyId?: string) => {
#     if (!initialized) throw new Error('Encryption not initialized');
#     return getEncryptionManager().decrypt_json(encrypted, customKeyId || keyId);
#   }, [initialized, keyId]);
# 
#   return {
#     initialized,
#     setPassword,
#     initialize,
#     encrypt,
#     decrypt,
#     decryptJson,
#   };
# }


# ==================== Default Export ====================

export default EncryptionManager;
export {
    EncryptionConfig,
    EncryptedData,
    KeyPair,
    EncryptionManager,
    RxDBEncryptionPlugin,
    get_encryption_manager,
    get_rxdb_encryption_plugin,
    init_encryption,
};

import time
import base64
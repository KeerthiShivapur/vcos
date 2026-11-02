"""
VAPID Key Management for Web Push Notifications

Provides utilities for generating, storing, and managing VAPID keys
for Web Push Protocol authentication.
"""

import base64
import json
import os
import secrets
from dataclasses import dataclass, field
from typing import Optional, Tuple
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import hashes

from app.core.config import get_settings


@dataclass
class VAPIDKeys:
    """Container for VAPID key pair."""
    private_key: str  # PEM format
    public_key: str   # PEM format
    public_key_base64url: str  # Base64URL encoded for client
    
    def to_dict(self) -> dict:
        return {
            'private_key': self.private_key,
            'public_key': self.public_key,
            'public_key_base64url': self.public_key_base64url,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'VAPIDKeys':
        return cls(
            private_key=data['private_key'],
            public_key=data['public_key'],
            public_key_base64url=data['public_key_base64url'],
        )


class VAPIDKeyManager:
    """
    Manages VAPID keys for Web Push Protocol.
    
    Features:
    - Key generation (P-256 elliptic curve)
    - Key persistence (file/environment)
    - Key rotation support
    - Base64URL encoding for client use
    - Integration with pywebpush
    """
    
    def __init__(self, keys_dir: Optional[str] = None):
        self.keys_dir = keys_dir or os.path.join(os.getcwd(), 'keys', 'vapid')
        self._keys: Optional[VAPIDKeys] = None
        self._ensure_keys_dir()
    
    def _ensure_keys_dir(self) -> None:
        """Ensure keys directory exists."""
        os.makedirs(self.keys_dir, exist_ok=True)
    
    def generate_keys(self) -> VAPIDKeys:
        """
        Generate new VAPID key pair using P-256 curve.
        
        Returns:
            VAPIDKeys with private/public keys in PEM and base64url formats
        """
        # Generate private key using P-256 (secp256r1)
        private_key = ec.generate_private_key(ec.SECP256R1())
        public_key = private_key.public_key()
        
        # Serialize private key to PEM
        private_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode('utf-8')
        
        # Serialize public key to PEM
        public_pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode('utf-8')
        
        # Get raw public key coordinates for base64url
        public_numbers = public_key.public_numbers()
        x = public_numbers.x.to_bytes(32, byteorder='big')
        y = public_numbers.y.to_bytes(32, byteorder='big')
        # Uncompressed point format: 0x04 + x + y
        uncompressed = b'\x04' + x + y
        public_key_base64url = base64.urlsafe_b64encode(uncompressed).decode('utf-8').rstrip('=')
        
        keys = VAPIDKeys(
            private_key=private_pem,
            public_key=public_pem,
            public_key_base64url=public_key_base64url,
        )
        
        self._keys = keys
        return keys
    
    def save_keys(self, keys: Optional[VAPIDKeys] = None) -> None:
        """Save keys to file."""
        keys = keys or self._keys
        if not keys:
            raise ValueError("No keys to save")
        
        filepath = os.path.join(self.keys_dir, 'vapid_keys.json')
        with open(filepath, 'w') as f:
            json.dump(keys.to_dict(), f, indent=2)
        
        # Set restrictive permissions (owner read/write only)
        os.chmod(filepath, 0o600)
    
    def load_keys(self) -> Optional[VAPIDKeys]:
        """Load keys from file."""
        filepath = os.path.join(self.keys_dir, 'vapid_keys.json')
        
        if not os.path.exists(filepath):
            return None
        
        try:
            with open(filepath, 'r') as f:
                data = json.load(f)
            self._keys = VAPIDKeys.from_dict(data)
            return self._keys
        except Exception as e:
            print(f"Failed to load VAPID keys: {e}")
            return None
    
    def get_or_create_keys(self) -> VAPIDKeys:
        """Get existing keys or generate new ones."""
        keys = self.load_keys()
        if keys:
            return keys
        
        keys = self.generate_keys()
        self.save_keys(keys)
        return keys
    
    def get_public_key_base64url(self) -> str:
        """Get public key in base64url format for client."""
        keys = self.get_or_create_keys()
        return keys.public_key_base64url
    
    def get_private_key_pem(self) -> str:
        """Get private key in PEM format for server signing."""
        keys = self.get_or_create_keys()
        return keys.private_key
    
    def rotate_keys(self) -> VAPIDKeys:
        """Rotate keys - generate new pair and save."""
        old_keys = self._keys
        new_keys = self.generate_keys()
        self.save_keys(new_keys)
        
        # Keep old keys for transition period (optional)
        if old_keys:
            backup_path = os.path.join(self.keys_dir, f'vapid_keys_backup_{int(time.time())}.json')
            with open(backup_path, 'w') as f:
                json.dump(old_keys.to_dict(), f, indent=2)
        
        return new_keys
    
    def export_public_key_jwk(self) -> dict:
        """Export public key in JWK format for web push libraries."""
        keys = self.get_or_create_keys()
        
        # Parse public key to get coordinates
        public_key = serialization.load_pem_public_key(keys.public_key.encode())
        numbers = public_key.public_numbers()
        
        return {
            "kty": "EC",
            "crv": "P-256",
            "x": base64.urlsafe_b64encode(numbers.x.to_bytes(32, 'big')).decode().rstrip('='),
            "y": base64.urlsafe_b64encode(numbers.y.to_bytes(32, 'big')).decode().rstrip('='),
            "alg": "ES256",
            "use": "enc",
        }
    
    def sign_jwt(self, payload: dict, subject: str = "mailto:admin@vcos.io") -> str:
        """
        Sign JWT with VAPID private key for Web Push authentication.
        
        Args:
            payload: JWT payload
            subject: VAPID subject (mailto: or https://)
            
        Returns:
            JWT token string
        """
        import jwt
        from jwt.algorithms import ECAlgorithm
        
        private_key = serialization.load_pem_private_key(
            self.get_private_key_pem().encode(),
            password=None,
        )
        
        # Prepare claims
        now = int(time.time())
        claims = {
            **payload,
            "iss": subject,
            "exp": payload.get("exp", int(time.time()) + 12 * 3600),  # 12 hours
            "iat": payload.get("iat", now),
        }
        
        # Remove VAPID-specific fields from payload
        vapid_claims = {k: v for k, v in claims.items() if k not in ("aud", "sub")}
        
        return jwt.encode(
            vapid_claims,
            private_key,
            algorithm="ES256",
        )
    
    def verify_jwt(self, token: str, subject: str = "mailto:admin@vcos.io") -> dict:
        """Verify JWT signed with VAPID key."""
        import jwt
        
        public_key = serialization.load_pem_public_key(
            self.get_or_create_keys().public_key.encode(),
        )
        
        return jwt.decode(
            token,
            public_key,
            algorithms=["ES256"],
            audience=subject,
        )


# Global instance
_vapid_manager: Optional[VAPIDKeyManager] = None


def get_vapid_manager(keys_dir: Optional[str] = None) -> VAPIDKeyManager:
    """Get or create global VAPID key manager."""
    global _vapid_manager
    if _vapid_manager is None:
        _vapid_manager = VAPIDKeyManager(keys_dir)
    return _vapid_manager


def init_vapid_keys(keys_dir: Optional[str] = None) -> VAPIDKeys:
    """Initialize VAPID keys on startup."""
    manager = get_vapid_manager(keys_dir)
    return manager.get_or_create_keys()


# Utility functions for direct use

def generate_vapid_keys() -> VAPIDKeys:
    """Quick utility to generate VAPID keys."""
    return VAPIDKeyManager().generate_keys()


def get_vapid_public_key_base64url(keys_dir: Optional[str] = None) -> str:
    """Get VAPID public key in base64url format."""
    manager = get_vapid_manager(keys_dir)
    return manager.get_public_key_base64url()


def sign_vapid_jwt(payload: dict, subject: str = "mailto:admin@vcos.io", keys_dir: Optional[str] = None) -> str:
    """Sign JWT with VAPID private key."""
    manager = get_vapid_manager(keys_dir)
    return manager.sign_jwt(payload, subject)


def verify_vapid_jwt(token: str, subject: str = "mailto:admin@vcos.io", keys_dir: Optional[str] = None) -> dict:
    """Verify VAPID JWT."""
    manager = get_vapid_manager(keys_dir)
    return manager.verify_jwt(token, subject)


if __name__ == "__main__":
    import time
    # Quick test
    manager = VAPIDKeyManager("./test_keys")
    keys = manager.generate_keys()
    print("Generated VAPID Keys:")
    print(f"Public Key (base64url): {keys.public_key_base64url}")
    print(f"Private Key PEM:\n{keys.private_key}")
    print(f"Public Key PEM:\n{keys.public_key}")
    print(f"JWK: {json.dumps(manager.export_public_key_jwk(), indent=2)}")
    
    # Test JWT signing
    token = manager.sign_jwt({"test": "payload"})
    print(f"\nJWT Token: {token}")
    
    # Verify
    verified = manager.verify_jwt(token)
    print(f"Verified: {verified}")
"""
Authentication for WebSocket Gateway
"""

import time
from dataclasses import dataclass
from typing import Optional

import jwt
from jwt.exceptions import InvalidTokenError

from app.config import settings


@dataclass
class TokenData:
    user_id: str
    organization_id: str
    email: Optional[str] = None
    roles: list = None
    permissions: list = None
    exp: int = 0
    iat: int = 0


class AuthenticationError(Exception):
    """Authentication error"""
    pass


async def verify_token(
    token: str,
    secret: str,
    algorithm: str = "HS256",
) -> TokenData:
    """
    Verify JWT token and return token data
    
    Args:
        token: JWT token string
        secret: JWT secret key
        algorithm: JWT algorithm
        
    Returns:
        TokenData with user information
        
    Raises:
        AuthenticationError: If token is invalid
    """
    # Remove Bearer prefix if present
    if token.startswith("Bearer "):
        token = token[7:]
    
    try:
        # Decode token
        payload = jwt.decode(
            token,
            secret,
            algorithms=[algorithm],
            options={
                "verify_signature": True,
                "verify_exp": True,
                "verify_iat": True,
                "verify_aud": False,
            }
        )
        
        # Check expiration
        exp = payload.get("exp", 0)
        if exp and exp < time.time():
            raise AuthenticationError("Token has expired")
        
        # Extract user info
        user_id = payload.get("sub") or payload.get("user_id")
        if not user_id:
            raise AuthenticationError("Token missing user_id")
        
        organization_id = payload.get("org_id") or payload.get("organization_id")
        if not organization_id:
            raise AuthenticationError("Token missing organization_id")
        
        return TokenData(
            user_id=str(user_id),
            organization_id=str(organization_id),
            email=payload.get("email"),
            roles=payload.get("roles", []),
            permissions=payload.get("permissions", []),
            exp=exp,
            iat=payload.get("iat", 0),
        )
        
    except jwt.ExpiredSignatureError:
        raise AuthenticationError("Token has expired")
    except jwt.InvalidTokenError as e:
        raise AuthenticationError(f"Invalid token: {str(e)}")
    except Exception as e:
        raise AuthenticationError(f"Token verification failed: {str(e)}")


def create_token(
    user_id: str,
    organization_id: str,
    secret: str,
    algorithm: str = "HS256",
    expiry: int = 3600,
    **extra_claims
) -> str:
    """Create JWT token"""
    now = int(time.time())
    payload = {
        "sub": user_id,
        "org_id": organization_id,
        "iat": now,
        "exp": now + expiry,
        **extra_claims,
    }
    
    return jwt.encode(payload, secret, algorithm=algorithm)
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import jwt
from pwdlib import PasswordHash

from app.core.config import get_settings

_password_hash = PasswordHash.recommended()

ACCESS = "access"
REFRESH = "refresh"
PASSWORD_RESET = "password_reset"
EMAIL_VERIFY = "email_verify"
INVITE = "invite"
PORTAL = "portal"


def hash_password(password: str) -> str:
    return _password_hash.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return _password_hash.verify(plain, hashed)


def generate_token() -> str:
    """Cryptographically secure random token for invites / email verification."""
    return secrets.token_urlsafe(48)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _create_jwt(token_type: str, sub: str, org_id: str, expires_delta: timedelta, extra: Optional[dict[str, Any]] = None) -> str:
    settings = get_settings()
    now = _now()
    payload: dict[str, Any] = {
        "sub": sub,
        "org": org_id,
        "type": token_type,
        "iat": now,
        "exp": now + expires_delta,
        "jti": uuid.uuid4().hex,
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_access_token(user_id: str, org_id: str) -> str:
    settings = get_settings()
    return _create_jwt(
        ACCESS, user_id, org_id, timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )


def create_refresh_token(user_id: str, org_id: str, session_id: str) -> str:
    settings = get_settings()
    return _create_jwt(
        REFRESH,
        user_id,
        org_id,
        timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        {"sid": session_id},
    )


def create_password_reset_token(user_id: str, org_id: str) -> str:
    settings = get_settings()
    return _create_jwt(
        PASSWORD_RESET,
        user_id,
        org_id,
        timedelta(hours=settings.PASSWORD_RESET_TOKEN_EXPIRE_HOURS),
    )


def create_email_verification_token(user_id: str, org_id: str) -> str:
    settings = get_settings()
    return _create_jwt(
        EMAIL_VERIFY,
        user_id,
        org_id,
        timedelta(hours=settings.EMAIL_VERIFICATION_TOKEN_EXPIRE_HOURS),
    )


def create_invite_token() -> str:
    return generate_token()


def create_portal_token(portal_user_id: str, org_id: str) -> str:
    settings = get_settings()
    return _create_jwt(
        PORTAL, portal_user_id, org_id, timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    )


def decode_token(token: str, expected_type: Optional[str] = None) -> dict[str, Any]:
    settings = get_settings()
    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    if expected_type and payload.get("type") != expected_type:
        raise jwt.InvalidTokenError(f"Expected token type {expected_type}")
    return payload

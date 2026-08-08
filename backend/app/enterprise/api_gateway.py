"""API gateway service (Phase 15).

API key issuance/rotation/revocation, scoped access, per-key rate limiting
(in-memory sliding window) and API versioning metadata. Only key hashes are
stored; the plaintext secret is returned exactly once at creation.
"""

import hashlib
import secrets
import threading
import time
from collections import deque
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import ensure_aware, utcnow
from app.events.publisher import publish_event
from app.models.enterprise import ApiKey

API_VERSIONS = ["v1"]
DEFAULT_RATE_LIMIT = 120  # requests per minute per key

# (api_key_id, minute_bucket) -> deque of timestamps
_rate_buckets: dict[str, deque] = {}
_rate_lock = threading.Lock()


def _key_secret() -> tuple[str, str]:
    raw = "vcos_" + secrets.token_urlsafe(32)
    prefix = raw[:10]
    return raw, hashlib.sha256(raw.encode()).hexdigest()


class ApiGatewayService:
    async def create_key(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        name: str,
        scopes: Optional[list[str]] = None,
        rate_limit_per_minute: int = DEFAULT_RATE_LIMIT,
        expires_at: Optional[datetime] = None,
        actor_id: Optional[str] = None,
    ) -> dict[str, Any]:
        raw, key_hash = _key_secret()
        key = ApiKey(
            organization_id=organization_id,
            name=name,
            key_prefix=raw[:10],
            key_hash=key_hash,
            scopes=scopes or ["*"],
            rate_limit_per_minute=max(1, rate_limit_per_minute),
            expires_at=expires_at,
            status="active",
        )
        db.add(key)
        await db.flush()
        await publish_event(
            db,
            name="api.key.created",
            organization_id=organization_id,
            actor_id=actor_id,
            payload={"key_id": key.id, "name": name, "prefix": key.key_prefix},
        )
        return {
            "id": key.id,
            "name": key.name,
            "prefix": key.key_prefix,
            "scopes": key.scopes,
            "rate_limit_per_minute": key.rate_limit_per_minute,
            "expires_at": key.expires_at,
            "api_key": raw,  # only returned once
        }

    async def rotate_key(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        key_id: str,
        actor_id: Optional[str] = None,
    ) -> Optional[dict[str, Any]]:
        key = await self.get_key(db, organization_id, key_id)
        if key is None:
            return None
        raw, key_hash = _key_secret()
        key.key_hash = key_hash
        key.key_prefix = raw[:10]
        key.status = "active"
        await publish_event(
            db,
            name="api.key.rotated",
            organization_id=organization_id,
            actor_id=actor_id,
            payload={"key_id": key.id, "name": key.name},
        )
        return {
            "id": key.id,
            "name": key.name,
            "prefix": key.key_prefix,
            "api_key": raw,  # only returned once
        }

    async def revoke_key(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        key_id: str,
        actor_id: Optional[str] = None,
    ) -> bool:
        key = await self.get_key(db, organization_id, key_id)
        if key is None:
            return False
        key.status = "revoked"
        await publish_event(
            db,
            name="api.key.revoked",
            organization_id=organization_id,
            actor_id=actor_id,
            payload={"key_id": key.id, "name": key.name},
        )
        return True

    async def list_keys(
        self, db: AsyncSession, organization_id: str, status: Optional[str] = None
    ) -> list[ApiKey]:
        query = select(ApiKey).where(ApiKey.organization_id == organization_id)
        if status:
            query = query.where(ApiKey.status == status)
        result = await db.execute(query.order_by(ApiKey.created_at.desc()))
        return list(result.scalars().all())

    async def get_key(
        self, db: AsyncSession, organization_id: str, key_id: str
    ) -> Optional[ApiKey]:
        key = await db.get(ApiKey, key_id)
        if key is None or key.organization_id != organization_id:
            return None
        return key

    async def authenticate(self, db: AsyncSession, api_key: str) -> Optional[dict[str, Any]]:
        """Resolve a raw API key against stored hashes; refresh last_used_at."""
        if not api_key or not api_key.startswith("vcos_"):
            return None
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        key = (
            await db.execute(select(ApiKey).where(ApiKey.key_hash == key_hash))
        ).scalars().first()
        if key is None or key.status != "active":
            return None
        if key.expires_at and ensure_aware(key.expires_at) < utcnow():
            return None
        key.last_used_at = utcnow()
        return {
            "key_id": key.id,
            "organization_id": key.organization_id,
            "scopes": list(key.scopes or ["*"]),
            "rate_limit_per_minute": key.rate_limit_per_minute,
        }

    def rate_limit_check(self, key_id: str, rate_limit_per_minute: int) -> dict[str, Any]:
        """Sliding-window rate limit for a key; returns allowed/remaining/reset."""
        bucket = f"{key_id}:{int(time.time()) // 60}"
        now = time.time()
        with _rate_lock:
            window = _rate_buckets.setdefault(bucket, deque())
            while window and now - window[0] > 60:
                window.popleft()
            if len(window) >= rate_limit_per_minute:
                return {
                    "allowed": False,
                    "remaining": 0,
                    "reset_in_seconds": 60 - (now - int(time.time() // 60) * 60),
                }
            window.append(now)
            return {
                "allowed": True,
                "remaining": rate_limit_per_minute - len(window),
                "reset_in_seconds": 0,
            }

    def reset_rate_limits(self) -> None:
        """Test hook — clears the in-memory sliding window state."""
        with _rate_lock:
            _rate_buckets.clear()

    def version_info(self) -> dict[str, Any]:
        return {
            "versions": API_VERSIONS,
            "current": API_VERSIONS[-1],
            "path_prefix": "/api",
            "header": "X-API-Key",
            "rate_limit": f"{DEFAULT_RATE_LIMIT}/minute",
        }


api_gateway_service = ApiGatewayService()

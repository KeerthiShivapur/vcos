"""Security center service (Phase 15).

Security event ingestion and detection: brute-force detection from repeated
failed logins, IP restriction enforcement via the authentication policy,
event lifecycle (open -> reviewing -> resolved) and alert fan-out through the
event bus so workflow rules can react (security.alert).
"""

from datetime import timedelta
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import ensure_aware, utcnow
from app.enterprise.identity_service import identity_service
from app.events.publisher import publish_event
from app.models.enterprise import SecurityEvent

EVENT_TYPES = {
    "login.failed": "A login attempt failed",
    "login.locked": "An account was locked after repeated failures",
    "brute_force.detected": "Repeated failed logins from a single source",
    "key.rotated": "An API key was rotated",
    "key.revoked": "An API key was revoked",
    "ip.blocked": "A request from a restricted IP was blocked",
    "policy.violation": "A security policy violation was detected",
    "suspicious.activity": "Suspicious activity was detected",
}

BRUTE_FORCE_THRESHOLD = 5
BRUTE_FORCE_WINDOW_MINUTES = 10


class SecurityService:
    async def record(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        event_type: str,
        severity: str = "medium",
        title: Optional[str] = None,
        actor_id: Optional[str] = None,
        source_ip: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
        publish: bool = True,
    ) -> SecurityEvent:
        if severity not in ("low", "medium", "high", "critical"):
            severity = "medium"
        event = SecurityEvent(
            organization_id=organization_id,
            event_type=event_type,
            severity=severity,
            title=title or EVENT_TYPES.get(event_type, event_type),
            actor_id=actor_id,
            source_ip=source_ip,
            details=details or {},
            status="open",
        )
        db.add(event)
        await db.flush()
        if publish:
            await publish_event(
                db,
                name="security.alert",
                organization_id=organization_id,
                actor_id=actor_id,
                payload={
                    "event_id": event.id,
                    "event_type": event_type,
                    "severity": severity,
                    "source_ip": source_ip,
                },
            )
        return event

    async def detect_failed_login(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        email: str,
        source_ip: str,
    ) -> dict[str, Any]:
        """Record a failed login; flag brute force when a source repeats."""
        failed = await self.record(
            db,
            organization_id=organization_id,
            event_type="login.failed",
            severity="low",
            title=f"Failed login for {email}",
            source_ip=source_ip,
            details={"email": email},
            publish=False,
        )
        since = utcnow() - timedelta(minutes=BRUTE_FORCE_WINDOW_MINUTES)
        count = (
            await db.execute(
                select(func.count(SecurityEvent.id)).where(
                    SecurityEvent.organization_id == organization_id,
                    SecurityEvent.source_ip == source_ip,
                    SecurityEvent.event_type == "login.failed",
                    SecurityEvent.created_at >= since,
                )
            )
        ).scalar_one()
        brute_force = int(count) >= BRUTE_FORCE_THRESHOLD
        if brute_force:
            existing = (
                await db.execute(
                    select(SecurityEvent.id).where(
                        SecurityEvent.organization_id == organization_id,
                        SecurityEvent.source_ip == source_ip,
                        SecurityEvent.event_type == "brute_force.detected",
                        SecurityEvent.created_at >= since,
                    )
                )
            ).scalars().first()
            if existing is None:
                await self.record(
                    db,
                    organization_id=organization_id,
                    event_type="brute_force.detected",
                    severity="high",
                    title=f"Brute-force pattern from {source_ip}",
                    source_ip=source_ip,
                    details={"failed_count": int(count), "window_minutes": BRUTE_FORCE_WINDOW_MINUTES},
                )
        return {"event_id": failed.id, "failed_count": int(count), "brute_force": brute_force}

    async def list_events(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        status: Optional[str] = None,
        severity: Optional[str] = None,
        limit: int = 50,
    ) -> list[SecurityEvent]:
        query = select(SecurityEvent).where(SecurityEvent.organization_id == organization_id)
        if status:
            query = query.where(SecurityEvent.status == status)
        if severity:
            query = query.where(SecurityEvent.severity == severity)
        result = await db.execute(
            query.order_by(SecurityEvent.created_at.desc()).limit(min(limit, 200))
        )
        return list(result.scalars().all())

    async def resolve(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        event_id: str,
        resolved_by: str,
    ) -> Optional[SecurityEvent]:
        event = await db.get(SecurityEvent, event_id)
        if event is None or event.organization_id != organization_id:
            return None
        event.status = "resolved"
        event.resolved_by = resolved_by
        event.resolved_at = utcnow()
        return event

    async def enforce_ip(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        ip: str,
        actor_id: Optional[str] = None,
    ) -> bool:
        """Return False when the IP is outside the org policy allow list."""
        if await identity_service.ip_allowed(db, organization_id, ip):
            return True
        await self.record(
            db,
            organization_id=organization_id,
            event_type="ip.blocked",
            severity="medium",
            title=f"Blocked request from restricted IP {ip}",
            actor_id=actor_id,
            source_ip=ip,
            details={"policy": "ip_restrictions"},
        )
        return False

    async def auto_resolve_stale(
        self, db: AsyncSession, *, older_than_days: int = 14, limit: int = 200
    ) -> int:
        """Worker hook — close low-severity events that aged out."""
        cutoff = utcnow() - timedelta(days=older_than_days)
        result = await db.execute(
            select(SecurityEvent).where(
                SecurityEvent.status.in_(("open", "reviewing")),
                SecurityEvent.severity.in_(("low", "medium")),
                SecurityEvent.created_at < cutoff,
            ).limit(limit)
        )
        resolved = 0
        for event in result.scalars().all():
            event.status = "resolved"
            event.resolved_at = utcnow()
            resolved += 1
        return resolved


security_service = SecurityService()

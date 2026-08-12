"""Phase 9.14 — Autonomous notification engine.

The organization notifies itself. This engine watches the background
intelligence layer and pushes notifications to the right people:

    - high/critical strategic risks        -> executives (users with executive:view)
    - elevated/high burnout signals        -> the employee's manager + executives
    - repeated delay patterns              -> executives

Guardrails:
- Dedup window: a notification with the same (type, entity_type, entity_id,
  recipient) is only created once per 24h, so a persistent condition does not
  spam users while a freshly detected condition still surfaces immediately.
- Priority follows severity: critical risks -> urgent, high -> high,
  burnout -> normal (data-driven flag), patterns -> normal.
"""

import logging
from datetime import timedelta
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.models.employee import Employee
from app.models.executive import StrategicRisk
from app.models.intelligence import ACTIVE_PATTERN_STATUSES, BurnoutSignal, PatternDetection
from app.models.notification import Notification
from app.models.permission_helpers import users_with_permission
from app.services.notification_service import notification_service

logger = logging.getLogger("vcos.intelligence.notifications")

DEDUP_WINDOW_HOURS = 24


class NotificationEngine:
    async def generate(self, db: AsyncSession, *, organization_id: str) -> int:
        """Generate autonomous notifications; returns count created."""
        created = 0
        executives = await users_with_permission(db, organization_id=organization_id, code="executive:view")
        created += await self._risk_alerts(db, organization_id=organization_id, executives=executives)
        created += await self._burnout_alerts(db, organization_id=organization_id, executives=executives)
        created += await self._pattern_alerts(db, organization_id=organization_id, executives=executives)
        return created

    # -------------------------------------------------------------- sources

    async def _risk_alerts(self, db: AsyncSession, *, organization_id: str,
                           executives: list[str]) -> int:
        rows = (
            await db.execute(
                select(StrategicRisk).where(
                    StrategicRisk.organization_id == organization_id,
                    StrategicRisk.status == "open",
                    StrategicRisk.level.in_(("high", "critical")),
                )
            )
        ).scalars().all()
        created = 0
        for risk in rows:
            priority = "urgent" if risk.level == "critical" else "high"
            created += await self._notify_once(
                db, organization_id=organization_id,
                recipient_ids=executives,
                type="risk",
                title=f"{risk.level.title()} risk: {risk.title}",
                body=risk.description or "The background risk engine detected this risk automatically.",
                priority=priority,
                link="/executive?tab=risks",
                entity_type=risk.subject_type or "organization",
                entity_id=risk.subject_id or risk.id,
                metadata_payload={"risk_id": risk.id, "score": risk.score},
            )
        return created

    async def _burnout_alerts(self, db: AsyncSession, *, organization_id: str,
                              executives: list[str]) -> int:
        rows = (
            await db.execute(
                select(
                    BurnoutSignal,
                    Employee.display_name, Employee.first_name, Employee.last_name,
                    Employee.manager_id,
                )
                .join(Employee, Employee.id == BurnoutSignal.employee_id)
                .where(
                    BurnoutSignal.organization_id == organization_id,
                    BurnoutSignal.status == "open",
                    BurnoutSignal.level.in_(("elevated", "high")),
                )
            )
        ).all()
        created = 0
        for signal, display_name, first_name, last_name, manager_id in rows:
            full_name = display_name or f"{first_name} {last_name or ''}".strip()
            recipient_ids = set(executives)
            if manager_id:
                recipient_ids.add(manager_id)
            if not recipient_ids:
                continue
            created += await self._notify_once(
                db, organization_id=organization_id,
                recipient_ids=sorted(recipient_ids),
                type="burnout",
                title=f"Workload flag: {full_name} ({signal.level})",
                body=(
                    f"Workload patterns for {full_name} match a {signal.level} overload pattern. "
                    "This is a data-driven flag — review their task and meeting load."
                ),
                priority="normal",
                link="/intelligence?tab=burnout",
                entity_type="employee",
                entity_id=signal.employee_id,
                metadata_payload={"signal_id": signal.id, "score": signal.score},
            )
        return created

    async def _pattern_alerts(self, db: AsyncSession, *, organization_id: str,
                              executives: list[str]) -> int:
        rows = (
            await db.execute(
                select(PatternDetection).where(
                    PatternDetection.organization_id == organization_id,
                    PatternDetection.status.in_(ACTIVE_PATTERN_STATUSES),
                    PatternDetection.pattern_type == "repeated_delay",
                    PatternDetection.count >= 3,
                )
            )
        ).scalars().all()
        created = 0
        for pattern in rows:
            created += await self._notify_once(
                db, organization_id=organization_id,
                recipient_ids=executives,
                type="pattern",
                title=f"Repeated delay pattern: {pattern.title}",
                body=(
                    f"This pattern has been observed {pattern.count} times. "
                    "Review the root cause to break the cycle."
                ),
                priority="normal",
                link="/intelligence?tab=patterns",
                entity_type="pattern",
                entity_id=pattern.id,
                metadata_payload={"pattern_id": pattern.id, "count": pattern.count},
            )
        return created

    # -------------------------------------------------------------- helpers

    async def _notify_once(
        self, db: AsyncSession, *, organization_id: str, recipient_ids: list[str],
        type: str, title: str, body: Optional[str], priority: str,
        link: Optional[str], entity_type: str, entity_id: str,
        metadata_payload: dict[str, Any],
    ) -> int:
        """Create notifications unless a matching one exists in the dedup window."""
        cutoff = utcnow() - timedelta(hours=DEDUP_WINDOW_HOURS)
        seen_recipients = set()
        for recipient_id in recipient_ids:
            if await self._has_similar(
                db, organization_id=organization_id, type=type,
                entity_type=entity_type, entity_id=entity_id,
                recipient_id=recipient_id, cutoff=cutoff,
            ):
                seen_recipients.add(recipient_id)
        created = 0
        for recipient_id in recipient_ids:
            if recipient_id in seen_recipients:
                continue
            await notification_service.create(
                db,
                organization_id=organization_id,
                recipient_id=recipient_id,
                type=type,
                title=title,
                body=body,
                priority=priority,
                channel="in_app",
                link=link,
                entity_type=entity_type,
                entity_id=entity_id,
                metadata=metadata_payload,
            )
            created += 1
        return created

    async def _has_similar(
        self, db: AsyncSession, *, organization_id: str, type: str,
        entity_type: str, entity_id: str, recipient_id: str, cutoff,
    ) -> bool:
        row = await db.execute(
            select(Notification.id).where(
                Notification.organization_id == organization_id,
                Notification.type == type,
                Notification.entity_type == entity_type,
                Notification.entity_id == entity_id,
                Notification.recipient_id == recipient_id,
                Notification.created_at >= cutoff,
            )
        )
        return row.scalar_one_or_none() is not None


notification_engine = NotificationEngine()

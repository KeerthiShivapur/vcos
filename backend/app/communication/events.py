"""Shared event / notification / naming helpers for the communication module."""

import re
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.communication import CommunityMember
from app.models.employee import Employee

MENTION_RE = re.compile(r"@([\w.\-]+)")


async def emit_and_audit(
    db: AsyncSession,
    *,
    organization_id: str,
    name: str,
    actor: Optional[Employee],
    actor_user_id: Optional[str],
    ip_address: Optional[str],
    payload: Optional[dict[str, Any]] = None,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
) -> None:
    """Emit a domain event and write an audit log row (knowledge-style pipeline)."""
    from app.knowledge.knowledge_base import emit_and_audit as kb_emit_and_audit

    await kb_emit_and_audit(
        db,
        organization_id=organization_id,
        name=name,
        actor=actor,
        actor_user_id=actor_user_id,
        ip_address=ip_address,
        payload=payload,
        resource_type=resource_type or "communication",
        resource_id=resource_id,
    )


async def notify_user(
    db: AsyncSession,
    *,
    organization_id: str,
    recipient_id: str,
    type: str,
    title: str,
    body: Optional[str] = None,
    actor_id: Optional[str] = None,
    priority: str = "normal",
    link: Optional[str] = None,
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    metadata: Optional[dict[str, Any]] = None,
) -> None:
    from app.services.notification_service import notification_service

    if recipient_id == actor_id:
        return
    await notification_service.create(
        db,
        organization_id=organization_id,
        recipient_id=recipient_id,
        type=type,
        title=title,
        body=body,
        actor_id=actor_id,
        priority=priority,
        link=link,
        entity_type=entity_type,
        entity_id=entity_id,
        metadata=metadata,
    )


async def notify_community_members(
    db: AsyncSession,
    *,
    organization_id: str,
    community_id: str,
    type: str,
    title: str,
    body: Optional[str] = None,
    actor_id: Optional[str] = None,
    link: Optional[str] = None,
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    skip_user_ids: Optional[set[str]] = None,
) -> int:
    """Fan out a notification to every member of a community (except the actor)."""
    rows = (
        await db.execute(
            select(CommunityMember).where(
                CommunityMember.organization_id == organization_id,
                CommunityMember.community_id == community_id,
                CommunityMember.notifications_enabled.is_(True),
            )
        )
    ).scalars().all()
    skip = skip_user_ids or set()
    count = 0
    for member in rows:
        if member.employee_id == actor_id or member.employee_id in skip:
            continue
        user_id = await _user_id_for_employee(db, organization_id, member.employee_id)
        if not user_id:
            continue
        await notify_user(
            db,
            organization_id=organization_id,
            recipient_id=user_id,
            type=type,
            title=title,
            body=body,
            actor_id=actor_id,
            link=link,
            entity_type=entity_type,
            entity_id=entity_id,
        )
        count += 1
    return count


async def _user_id_for_employee(db: AsyncSession, organization_id: str, employee_id: str) -> Optional[str]:
    row = (
        await db.execute(
            select(Employee.user_id).where(
                Employee.organization_id == organization_id,
                Employee.id == employee_id,
            )
        )
    ).scalar_one_or_none()
    return row


async def _mention_handle_map(db: AsyncSession, organization_id: str) -> dict[str, str]:
    """Map `handle` (email local part, lowercased) -> employee id."""
    rows = (
        await db.execute(
            select(Employee.id, Employee.email).where(Employee.organization_id == organization_id)
        )
    ).all()
    out: dict[str, str] = {}
    for employee_id, email in rows:
        if email and "@" in email:
            out[email.split("@", 1)[0].lower()] = employee_id
    return out


async def notify_mentions(
    db: AsyncSession,
    *,
    organization_id: str,
    text: Optional[str],
    type: str,
    title: str,
    body: Optional[str] = None,
    actor_id: Optional[str],
    link: Optional[str],
    entity_type: Optional[str],
    entity_id: Optional[str],
    default_employee_ids: Optional[list[str]] = None,
) -> None:
    """Notify employees mentioned as @handle (handle = email local part) plus extras."""
    mentioned: list[str] = []
    if text:
        handles = {handle.lower() for handle in MENTION_RE.findall(text)}
        if handles:
            handle_map = await _mention_handle_map(db, organization_id)
            for handle in handles:
                employee_id = handle_map.get(handle)
                if employee_id and employee_id not in mentioned:
                    mentioned.append(employee_id)
    for employee_id in (default_employee_ids or []):
        if employee_id not in mentioned:
            mentioned.append(employee_id)
    for employee_id in mentioned:
        user_id = await _user_id_for_employee(db, organization_id, employee_id)
        if not user_id:
            continue
        await notify_user(
            db,
            organization_id=organization_id,
            recipient_id=user_id,
            type=type,
            title=title,
            body=body,
            actor_id=actor_id,
            link=link,
            entity_type=entity_type,
            entity_id=entity_id,
        )


async def employee_name_map(db: AsyncSession, employee_ids: list[str]) -> dict[str, str]:
    ids = [eid for eid in set(employee_ids or []) if eid]
    if not ids:
        return {}
    rows = (
        await db.execute(
            select(
                Employee.id,
                Employee.display_name,
                Employee.first_name,
                Employee.last_name,
            ).where(Employee.id.in_(ids))
        )
    ).all()
    out: dict[str, str] = {}
    for row in rows:
        out[row[0]] = row[1] or " ".join(part for part in (row[2], row[3]) if part) or row[0]
    return out

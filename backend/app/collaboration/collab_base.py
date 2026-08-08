"""Shared helpers for the collaboration module (Phase 6)."""

import json
import secrets
import string
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.employee import Employee

CODE_ALPHABET = string.ascii_uppercase + string.digits


def new_join_code(length: int = 8) -> str:
    """Human-friendly join code (no ambiguous characters)."""
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def safe_json(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return json.dumps(value, default=str)


def parse_json(value: Optional[str]) -> Optional[dict[str, Any]]:
    if not value:
        return None
    try:
        data = json.loads(value)
        return data if isinstance(data, dict) else None
    except (TypeError, ValueError):
        return None


async def emit_and_audit(
    db: AsyncSession,
    *,
    organization_id: str,
    name: str,
    actor: Optional[Employee],
    actor_user_id: Optional[str],
    ip_address: Optional[str],
    payload: Optional[dict[str, Any]] = None,
    resource_type: str = "collaboration",
    resource_id: Optional[str] = None,
) -> None:
    """Emit a domain event and write an audit log row (same pipeline as knowledge)."""
    from app.knowledge.knowledge_base import emit_and_audit as kb_emit_and_audit

    await kb_emit_and_audit(
        db,
        organization_id=organization_id,
        name=name,
        actor=actor,
        actor_user_id=actor_user_id,
        ip_address=ip_address,
        payload=payload,
        resource_type=resource_type,
        resource_id=resource_id,
    )


async def notify_employee_ids(
    db: AsyncSession,
    *,
    organization_id: str,
    employee_ids: list[str],
    type: str,
    title: str,
    body: Optional[str] = None,
    actor: Optional[Employee] = None,
    priority: str = "normal",
    link: Optional[str] = None,
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    exclude_ids: Optional[set[str]] = None,
) -> int:
    from app.services.work_alerts import notify_employees

    return await notify_employees(
        db,
        organization_id=organization_id,
        employee_ids=employee_ids,
        type=type,
        title=title,
        body=body,
        actor_id=actor.user_id if actor else None,
        priority=priority,
        link=link,
        entity_type=entity_type,
        entity_id=entity_id,
        exclude_ids=exclude_ids,
    )


async def resolve_employee(db: AsyncSession, organization_id: str, employee_id: str) -> Employee:
    employee = await db.get(Employee, employee_id)
    if employee is None or employee.organization_id != organization_id:
        raise ValueError("Invalid employee reference")
    return employee

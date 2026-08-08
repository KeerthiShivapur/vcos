"""Work alerts — turn work domain events into in-app notifications (Phase 3).

Every work mutation already emits an event on the event bus. This helper
routes the same moments into the notification stream so assignees, attendees,
approvers and risk owners hear about them in-app without an email dependency.
"""

from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession


async def notify_employee(
    db: AsyncSession,
    *,
    organization_id: str,
    employee_id: Optional[str],
    type: str,
    title: str,
    body: Optional[str] = None,
    actor_id: Optional[str] = None,
    priority: str = "normal",
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    link: Optional[str] = None,
    metadata: Optional[dict[str, Any]] = None,
) -> bool:
    """Notify the user behind an employee record. No-op when unresolved."""
    if not employee_id:
        return False
    from app.models.employee import Employee

    employee = await db.get(Employee, employee_id)
    if employee is None or employee.user_id is None:
        return False
    from app.services.notification_service import notification_service

    await notification_service.create(
        db,
        organization_id=organization_id,
        recipient_id=employee.user_id,
        actor_id=actor_id,
        type=type,
        title=title,
        body=body,
        priority=priority,
        entity_type=entity_type,
        entity_id=entity_id,
        link=link,
        metadata=metadata,
    )
    return True


async def notify_employees(
    db: AsyncSession,
    *,
    organization_id: str,
    employee_ids: list[str],
    type: str,
    title: str,
    body: Optional[str] = None,
    actor_id: Optional[str] = None,
    priority: str = "normal",
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    link: Optional[str] = None,
    exclude_ids: Optional[set[str]] = None,
) -> int:
    """Notify every employee in a list (skipping duplicates and exclusions)."""
    seen: set[str] = set()
    created = 0
    for employee_id in employee_ids:
        if not employee_id or employee_id in seen:
            continue
        if exclude_ids and employee_id in exclude_ids:
            continue
        seen.add(employee_id)
        if await notify_employee(
            db,
            organization_id=organization_id,
            employee_id=employee_id,
            type=type,
            title=title,
            body=body,
            actor_id=actor_id,
            priority=priority,
            entity_type=entity_type,
            entity_id=entity_id,
            link=link,
        ):
            created += 1
    return created

"""Work-domain audit trail — records work actions through audit_service.

Every service-level mutation in the work domain writes an audit entry so
project/task/epic/milestone/sprint/goal/meeting/approval/risk/dependency
history is queryable via GET /audit with resource_type filters.
"""

from typing import Any, Optional

from app.models.employee import Employee
from app.services.audit_service import audit_service


def _actor_parts(actor: Optional[Employee]) -> tuple[Optional[str], Optional[str]]:
    if actor is None:
        return None, None
    return actor.user_id or actor.id, actor.email


async def record(
    db,
    *,
    organization_id: str,
    action: str,
    actor: Optional[Employee] = None,
    actor_id: Optional[str] = None,
    ip_address: Optional[str] = None,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    details: Optional[dict[str, Any]] = None,
    severity: str = "info",
    outcome: str = "success",
) -> None:
    aid, aemail = _actor_parts(actor)
    await audit_service.log(
        db,
        organization_id=organization_id,
        action=action,
        actor_id=actor_id or aid,
        actor_email=aemail,
        ip_address=ip_address,
        resource_type=resource_type,
        resource_id=resource_id,
        details=details,
        severity=severity,
        outcome=outcome,
    )

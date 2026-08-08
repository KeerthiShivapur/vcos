"""Approval workflow bridge — knowledge entities ride the existing approval bus.

Submitting a document or policy for review creates a real Approval record so
approvers see it in the approvals inbox, and the decision flows back through
`approve`/`reject` on the knowledge API.
"""

from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.employee import Employee
from app.models.knowledge import Document, Policy


def _kind_of(entity) -> str:
    kind = type(entity).__name__.lower()
    return "wiki" if kind == "wikipage" else kind


class WorkflowService:
    async def create_approval(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        entity,
        actor: Optional[Employee],
        approver_id: Optional[str] = None,
    ) -> Optional[object]:
        from app.work.approval_service import approval_service

        kind = _kind_of(entity)
        approver = None
        if isinstance(entity, Policy):
            approver = entity.approver_id or approver_id
        elif isinstance(entity, Document):
            approver = approver_id or (entity.owner_id if entity.owner_id != (actor.id if actor else None) else None)
        if approver is None:
            return None
        return await approval_service.create(
            db,
            organization_id=organization_id,
            data={
                "approval_type": "document",
                "title": f"Approve {kind}: {entity.title}",
                "description": "Knowledge workflow approval",
                "requester_id": actor.id if actor else None,
                "approver_id": approver,
                "priority": "normal",
                "entity_type": kind,
                "entity_id": entity.id,
            },
            actor=actor,
        )


workflow_service = WorkflowService()

"""Document service — the document management core (Phase 4.1)."""

from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.knowledge.crud_base import KnowledgeCrud
from app.models.employee import Employee
from app.models.knowledge import Document


class DocumentService(KnowledgeCrud):
    model = Document
    kind = "document"

    async def submit_for_review(
        self, db: AsyncSession, *, organization_id: str, entity_id: str, actor: Optional[Employee], ip_address: Optional[str], approver_id: Optional[str] = None,
    ) -> Any:
        entity = await self.get(db, organization_id=organization_id, entity_id=entity_id)
        if entity is None:
            return None
        await self.set_status(
            db, organization_id=organization_id, entity_id=entity_id, status="in_review", actor=actor, ip_address=ip_address,
            note="Submitted for review",
        )
        from app.knowledge.workflow_service import workflow_service

        await workflow_service.create_approval(
            db, organization_id=organization_id, entity=entity, actor=actor, approver_id=approver_id
        )
        return entity

    async def approve(
        self, db: AsyncSession, *, organization_id: str, entity_id: str, actor: Optional[Employee], ip_address: Optional[str], note: Optional[str] = None,
    ) -> Any:
        entity = await self.get(db, organization_id=organization_id, entity_id=entity_id)
        if entity is None:
            return None
        await self.set_status(
            db, organization_id=organization_id, entity_id=entity_id, status="published", actor=actor, ip_address=ip_address, note=note or "Approved",
        )
        return entity


document_service = DocumentService()

from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workspace import Workspace, WorkspaceItem


class WorkspaceService:
    async def get_or_create(self, db: AsyncSession, *, user_id: str, organization_id: str) -> Workspace:
        workspace = (
            await db.execute(
                select(Workspace).where(Workspace.user_id == user_id, Workspace.organization_id == organization_id)
            )
        ).scalar_one_or_none()
        if workspace is None:
            workspace = Workspace(user_id=user_id, organization_id=organization_id)
            db.add(workspace)
            await db.flush()
        return workspace

    async def update(self, db: AsyncSession, workspace: Workspace, data: dict) -> Workspace:
        for key, value in data.items():
            if value is not None and hasattr(workspace, key):
                setattr(workspace, key, value)
        await db.flush()
        return workspace

    async def add_item(self, db: AsyncSession, *, workspace: Workspace, data: dict) -> WorkspaceItem:
        item = WorkspaceItem(
            workspace_id=workspace.id,
            user_id=workspace.user_id,
            organization_id=workspace.organization_id,
            kind=data["kind"],
            title=data["title"],
            content=data.get("content"),
            link=data.get("link"),
            entity_type=data.get("entity_type"),
            entity_id=data.get("entity_id"),
            pinned=data["kind"] in ("pin", "shortcut"),
        )
        db.add(item)
        await db.flush()
        return item

    async def list_items(
        self,
        db: AsyncSession,
        *,
        user_id: str,
        organization_id: str,
        kind: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[WorkspaceItem], int]:
        filters = [WorkspaceItem.user_id == user_id, WorkspaceItem.organization_id == organization_id]
        if kind:
            filters.append(WorkspaceItem.kind == kind)
        total = (await db.execute(select(func.count()).select_from(WorkspaceItem).where(*filters))).scalar_one()
        result = await db.execute(
            select(WorkspaceItem)
            .where(*filters)
            .order_by(WorkspaceItem.pinned.desc(), WorkspaceItem.updated_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(result.scalars().all()), total

    async def update_item(self, db: AsyncSession, item: WorkspaceItem, data: dict) -> WorkspaceItem:
        for key, value in data.items():
            if value is not None and hasattr(item, key):
                setattr(item, key, value)
        await db.flush()
        return item


workspace_service = WorkspaceService()

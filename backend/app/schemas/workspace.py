from typing import Optional

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class WorkspaceOut(ORMModel):
    id: str
    user_id: str
    daily_goal: Optional[str] = None
    onboarding_completed: bool
    created_at: object
    updated_at: object


class WorkspaceUpdate(BaseModel):
    daily_goal: Optional[str] = None
    onboarding_completed: Optional[bool] = None


class WorkspaceItemOut(ORMModel):
    id: str
    kind: str
    title: str
    content: Optional[str] = None
    link: Optional[str] = None
    entity_type: Optional[str] = None
    entity_id: Optional[str] = None
    pinned: bool
    created_at: object
    updated_at: object


class WorkspaceItemCreate(BaseModel):
    kind: str = Field(pattern="^(note|bookmark|shortcut|pin|reminder)$")
    title: str = Field(min_length=1, max_length=300)
    content: Optional[str] = None
    link: Optional[str] = None
    entity_type: Optional[str] = None
    entity_id: Optional[str] = None


class WorkspaceItemUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    link: Optional[str] = None
    pinned: Optional[bool] = None


class WorkspaceDashboard(BaseModel):
    workspace: WorkspaceOut
    items: list = []
    recent_items: list = []
    pinned_items: list = []
    notes_count: int
    bookmarks_count: int


class AICompanionStatus(BaseModel):
    available: bool
    provider: str
    model: str
    message: str

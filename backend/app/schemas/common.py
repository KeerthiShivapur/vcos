from datetime import datetime
from typing import Generic, List, Optional, TypeVar

from pydantic import BaseModel, ConfigDict

T = TypeVar("T")


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Message(BaseModel):
    message: str
    detail: Optional[str] = None


class Paginated(BaseModel, Generic[T]):
    items: List[T]
    total: int
    page: int
    page_size: int
    pages: int


class PageParams(BaseModel):
    page: int = 1
    page_size: int = 20

    def clamp(self, max_size: int = 100) -> "PageParams":
        page = max(1, self.page)
        page_size = min(max(1, self.page_size), max_size)
        return PageParams(page=page, page_size=page_size)


class TimeStamped(BaseModel):
    created_at: datetime
    updated_at: datetime


class UserSummary(ORMModel):
    id: str
    full_name: str
    email: str
    username: Optional[str] = None
    avatar_url: Optional[str] = None
    role: str
    job_title: Optional[str] = None
    status: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class RoleBrief(ORMModel):
    id: str
    name: str
    code: str
    is_system: bool
    is_default: bool

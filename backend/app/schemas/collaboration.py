"""Phase 6 — collaboration schemas (rooms, sessions, participants, notes)."""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class RoomCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    room_type: str = Field(default="meeting", pattern="^(meeting|virtual_office|project|department|team|event|standup)$")
    description: Optional[str] = None
    capacity: int = Field(default=8, ge=1, le=500)
    location: Optional[str] = None
    status: str = Field(default="available", pattern="^(available|scheduled|occupied|maintenance)$")
    department_id: Optional[str] = None
    team_id: Optional[str] = None
    project_id: Optional[str] = None
    created_by: Optional[str] = None
    is_public: bool = True
    allow_recording: bool = True
    settings: Optional[dict[str, Any]] = None


class RoomUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    room_type: Optional[str] = Field(default=None, pattern="^(meeting|virtual_office|project|department|team|event|standup)$")
    description: Optional[str] = None
    capacity: Optional[int] = Field(default=None, ge=1, le=500)
    location: Optional[str] = None
    status: Optional[str] = Field(default=None, pattern="^(available|scheduled|occupied|maintenance)$")
    department_id: Optional[str] = None
    team_id: Optional[str] = None
    project_id: Optional[str] = None
    is_public: Optional[bool] = None
    allow_recording: Optional[bool] = None
    settings: Optional[dict[str, Any]] = None


class RoomOut(BaseModel):
    id: str
    name: str
    room_type: str
    description: Optional[str] = None
    capacity: int
    location: Optional[str] = None
    status: str
    department_id: Optional[str] = None
    team_id: Optional[str] = None
    project_id: Optional[str] = None
    created_by: Optional[str] = None
    is_public: bool
    allow_recording: bool
    settings: Optional[dict[str, Any]] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class SessionCreate(BaseModel):
    room_id: Optional[str] = None
    timezone: Optional[str] = None
    max_participants: int = Field(default=50, ge=1, le=1000)
    is_recording: bool = False
    is_captions_enabled: bool = False
    is_translation_enabled: bool = False
    settings: Optional[dict[str, Any]] = None


class ParticipantOut(BaseModel):
    id: str
    session_id: str
    employee_id: str
    name: Optional[str] = None
    designation: Optional[str] = None
    avatar_url: Optional[str] = None
    role: str
    status: str
    device: Optional[str] = None
    mic_enabled: bool = False
    camera_enabled: bool = False
    screen_sharing: bool = False
    is_present: bool = False
    joined_at: Optional[datetime] = None
    left_at: Optional[datetime] = None
    last_active_at: Optional[datetime] = None
    speaking_seconds: int = 0
    messages_count: int = 0
    raised_hand: bool = False


class SessionOut(BaseModel):
    id: str
    meeting_id: str
    room_id: Optional[str] = None
    status: str
    meeting_code: str
    timezone: str
    max_participants: int
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    duration_seconds: int = 0
    is_recording: bool = False
    is_captions_enabled: bool = False
    is_translation_enabled: bool = False
    is_transcribing: bool = False
    settings: Optional[dict[str, Any]] = None
    participants: list[ParticipantOut] = []
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class JoinBody(BaseModel):
    device: Optional[str] = None


class InviteBody(BaseModel):
    employee_ids: list[str]
    message: Optional[str] = None


class NoteCreate(BaseModel):
    content: str = ""
    session_id: Optional[str] = None


class NoteUpdate(BaseModel):
    content: str


class NoteOut(BaseModel):
    id: str
    meeting_id: str
    session_id: Optional[str] = None
    author_id: Optional[str] = None
    author_name: Optional[str] = None
    content: str
    version: int = 1
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class ChatSendBody(BaseModel):
    content: str = Field(min_length=1, max_length=4000)
    reply_to: Optional[str] = None


class ChatMessageOut(BaseModel):
    id: str
    meeting_id: str
    session_id: Optional[str] = None
    employee_id: Optional[str] = None
    sender_name: Optional[str] = None
    sender_designation: Optional[str] = None
    avatar_url: Optional[str] = None
    content: str
    kind: str = "message"
    reply_to: Optional[str] = None
    created_at: Optional[datetime] = None


class WhiteboardUpdate(BaseModel):
    content: dict[str, Any]
    version: int = Field(ge=0)


class WhiteboardOut(BaseModel):
    id: str
    meeting_id: str
    session_id: Optional[str] = None
    content: dict[str, Any] = {}
    version: int = 1
    created_by: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

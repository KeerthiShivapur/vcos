"""Calendar Event models."""

from datetime import datetime
from typing import Optional, List
from sqlalchemy import DateTime, ForeignKey, String, Text, JSON, Boolean, Index, UniqueConstraint, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, gen_uuid


class CalendarEventStatus(str):
    CONFIRMED = "confirmed"
    TENTATIVE = "tentative"
    CANCELLED = "cancelled"


class CalendarEventVisibility(str):
    PUBLIC = "public"
    PRIVATE = "private"
    CONFIDENTIAL = "confidential"


class RecurrenceFrequency(str):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    YEARLY = "yearly"
    CUSTOM = "custom"


class CalendarEvent(Base, TimestampMixin):
    __tablename__ = "calendar_events"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    calendar_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("calendars.id", ondelete="SET NULL"), index=True
    )
    creator_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), default="confirmed", nullable=False)
    visibility: Mapped[str] = mapped_column(String(20), default="private", nullable=False)
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    timezone: Mapped[str] = mapped_column(String(50), default="UTC", nullable=False)
    all_day: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    location: Mapped[Optional[str]] = mapped_column(String(500))
    meeting_link: Mapped[Optional[str]] = mapped_column(String(500))
    meeting_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("meetings.id", ondelete="SET NULL"), index=True
    )
    project_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"), index=True
    )
    task_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("tasks.id", ondelete="SET NULL"), index=True
    )
    color: Mapped[Optional[str]] = mapped_column(String(7))
    is_recurring: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    recurrence_rule: Mapped[Optional[str]] = mapped_column(String(500))
    recurrence_end: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    parent_event_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("calendar_events.id", ondelete="SET NULL"), index=True
    )
    reminders: Mapped[List[dict]] = mapped_column(JSON, default=list)
    attendees: Mapped[List[dict]] = mapped_column(JSON, default=list)
    tags: Mapped[List[str]] = mapped_column(JSON, default=list)
    calendareventstatus_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    calendar: Mapped[Optional["Calendar"]] = relationship()
    creator: Mapped["Employee"] = relationship(back_populates="created_events")
    attendees_list: Mapped[List["CalendarEventAttendee"]] = relationship(back_populates="event", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_calendar_events_org_time", "organization_id", "start_time"),
        Index("ix_calendar_events_org_creator", "organization_id", "creator_id"),
        Index("ix_calendar_events_time_range", "start_time", "end_time"),
    )


class Calendar(Base, TimestampMixin):
    __tablename__ = "calendars"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    owner_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    color: Mapped[Optional[str]] = mapped_column(String(7))
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_shared: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    time_zone: Mapped[str] = mapped_column(String(50), default="UTC", nullable=False)
    settings: Mapped[dict] = mapped_column(JSON, default=dict)

    organization: Mapped["Organization"] = relationship()
    owner: Mapped["Employee"] = relationship(back_populates="owned_calendars")
    events: Mapped[List["CalendarEvent"]] = relationship(back_populates="calendar")

    __table_args__ = (
        UniqueConstraint("organization_id", "name", "owner_id", name="uq_calendars_org_name_owner"),
        Index("ix_calendars_org_owner", "organization_id", "owner_id"),
    )


class CalendarEventAttendee(Base, TimestampMixin):
    __tablename__ = "calendar_event_attendees"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    event_id: Mapped[str] = mapped_column(
        ForeignKey("calendar_events.id", ondelete="CASCADE"), index=True, nullable=False
    )
    employee_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    status: Mapped[str] = mapped_column(String(24), default="pending", nullable=False)
    role: Mapped[str] = mapped_column(String(20), default="attendee", nullable=False)
    responded_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    event: Mapped["CalendarEvent"] = relationship(back_populates="attendees_list")
    employee: Mapped["Employee"] = relationship()

    __table_args__ = (
        UniqueConstraint("event_id", "employee_id", name="uq_cal_event_attendees_event_emp"),
    )


class RecurringEvent(Base, TimestampMixin):
    __tablename__ = "recurring_events"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    creator_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    frequency: Mapped[str] = mapped_column(String(20), nullable=False)
    interval: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    days_of_week: Mapped[List[int]] = mapped_column(JSON, default=list)
    day_of_month: Mapped[Optional[int]] = mapped_column(Integer)
    month_of_year: Mapped[Optional[int]] = mapped_column(Integer)
    start_time: Mapped[str] = mapped_column(String(5), nullable=False)
    end_time: Mapped[str] = mapped_column(String(5), nullable=False)
    timezone: Mapped[str] = mapped_column(String(50), default="UTC", nullable=False)
    start_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    exceptions: Mapped[List[datetime]] = mapped_column(JSON, default=list)
    calendar_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("calendars.id", ondelete="SET NULL"), index=True
    )
    template_event_id: Mapped[str] = mapped_column(
        ForeignKey("calendar_events.id", ondelete="CASCADE"), index=True, nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    __table_args__ = (
        Index("ix_recurring_events_org_active", "organization_id", "is_active"),
    )


class CalendarShare(Base, TimestampMixin):
    __tablename__ = "calendar_shares"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    calendar_id: Mapped[str] = mapped_column(
        ForeignKey("calendars.id", ondelete="CASCADE"), index=True, nullable=False
    )
    shared_with_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    shared_by: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    permission: Mapped[str] = mapped_column(String(20), default="read", nullable=False)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    message: Mapped[Optional[str]] = mapped_column(Text)

    __table_args__ = (
        UniqueConstraint("calendar_id", "shared_with_id", name="uq_calendar_shares_cal_emp"),
    )
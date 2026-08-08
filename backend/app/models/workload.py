"""Workload snapshots — capacity and utilization per employee (Phase 3)."""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base
from app.models.organization import gen_uuid


class WorkloadSnapshot(Base):
    __tablename__ = "workload_snapshots"
    __table_args__ = (
        Index("ix_workload_org_period", "organization_id", "period_start"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    employee_id: Mapped[str] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True)
    period_start: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    period_end: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    capacity_hours: Mapped[float] = mapped_column()  # Float
    allocated_hours: Mapped[float] = mapped_column()  # Float
    utilization: Mapped[float] = mapped_column()  # 0-100
    tasks_count: Mapped[int] = mapped_column(Integer, default=0)
    meetings_hours: Mapped[float] = mapped_column(default=0)
    is_overloaded: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

"""Backfill and enforce NOT NULL on core entity timestamps

Fixes a pre-existing model defect: Project, Roadmap, Epic, Milestone, Sprint,
Approval, Risk, Department, BusinessUnit, Location and ExpertiseScore
redeclared created_at/updated_at without the TimestampMixin default,
so ORM inserts persisted NULL timestamps. This migration backfills the
existing NULL rows (at migration time) and converges the schema with the
corrected models by enforcing NOT NULL.

Revision ID: 9f3c1a7d52e4
Revises: 8ca2a1cf24bf
Create Date: 2026-10-18 03:20:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '9f3c1a7d52e4'
down_revision: Union[str, None] = '8ca2a1cf24bf'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLES = [
    "approvals",
    "risks",
    "departments",
    "business_units",
    "locations",
    "expertise_scores",
    "projects",
    "roadmaps",
    "epics",
    "milestones",
    "sprints",
]


def upgrade() -> None:
    for table in TABLES:
        for column in ("created_at", "updated_at"):
            op.execute(
                sa.text(
                    f'UPDATE {table} SET {column} = now() WHERE {column} IS NULL'
                )
            )
            op.alter_column(
                table,
                column,
                existing_type=sa.DateTime(timezone=True),
                nullable=False,
            )


def downgrade() -> None:
    for table in TABLES:
        for column in ("created_at", "updated_at"):
            op.alter_column(
                table,
                column,
                existing_type=sa.DateTime(timezone=True),
                nullable=True,
            )

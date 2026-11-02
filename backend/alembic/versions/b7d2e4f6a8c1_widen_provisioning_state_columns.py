"""Widen provisionings.state and previous_state to VARCHAR(40)

Fixes a pre-existing model defect surfaced by PostgreSQL acceptance tests:
Provisioning.state / previous_state were String(20), but the canonical
provisioning state machine (PROVISIONING_STATE_ORDER) contains values up to
28 characters (e.g. "company_brain_initialization", "governance_initialized").
SQLite ignores VARCHAR length limits, so the defect only fails on PostgreSQL
with StringDataRightTruncationError.

Revision ID: b7d2e4f6a8c1
Revises: 9f3c1a7d52e5
Create Date: 2026-10-18 05:10:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b7d2e4f6a8c1'
down_revision: Union[str, None] = '9f3c1a7d52e5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


COLUMNS = ("state", "previous_state")


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "provisionings" not in inspector.get_table_names():
        return
    for column in COLUMNS:
        op.alter_column(
            "provisionings",
            column,
            existing_type=sa.String(20),
            type_=sa.String(40),
            existing_nullable=(column == "previous_state"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "provisionings" not in inspector.get_table_names():
        return
    for column in COLUMNS:
        op.alter_column(
            "provisionings",
            column,
            existing_type=sa.String(40),
            type_=sa.String(20),
            existing_nullable=(column == "previous_state"),
        )

"""Widen external_events.webhook_delivery_id to VARCHAR(64)

Fixes a model defect surfaced during webhook ingestion review:
ExternalEvent.webhook_delivery_id was String(32), but real provider delivery
identifiers are longer — GitHub sends a 36-character delivery UUID via the
X-GitHub-Delivery header, stored verbatim by WebhookIngestionService.
PostgreSQL rejects values longer than the column limit with
StringDataRightTruncationError; SQLite ignores VARCHAR limits.

Revision ID: c9a1f4e7b2d8
Revises: 9f3c1a7d52e8
Create Date: 2026-10-18 15:20:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c9a1f4e7b2d8'
down_revision: Union[str, None] = '9f3c1a7d52e8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "external_events" not in inspector.get_table_names():
        return
    op.alter_column(
        "external_events",
        "webhook_delivery_id",
        existing_type=sa.String(32),
        type_=sa.String(64),
        existing_nullable=True,
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "external_events" not in inspector.get_table_names():
        return
    op.alter_column(
        "external_events",
        "webhook_delivery_id",
        existing_type=sa.String(64),
        type_=sa.String(32),
        existing_nullable=True,
    )

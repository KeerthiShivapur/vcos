"""merge heads

Revision ID: f5cd24c9e5bd
Revises: 9f3c1a7d52e5, b7d2e4f6a8c1
Create Date: 2026-10-18 11:14:40.213257
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f5cd24c9e5bd'
down_revision: Union[str, None] = ('9f3c1a7d52e5', 'b7d2e4f6a8c1')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass

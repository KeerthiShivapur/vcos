"""Merge multi-company entity fields and widen decision ID columns

Revision ID: 14d666a9c15b
Revises: 0d2cda4db5de, e63b67b815b7
Create Date: 2026-10-05 12:13:09.776750
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '14d666a9c15b'
down_revision: Union[str, None] = ('0d2cda4db5de', 'e63b67b815b7')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass

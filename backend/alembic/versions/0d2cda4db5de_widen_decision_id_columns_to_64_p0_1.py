"""widen_decision_id_columns_to_64_p0_1

Revision ID: 0d2cda4db5de
Revises: 
Create Date: 2026-08-22 15:24:37.093413
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0d2cda4db5de'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Slice 4H.7 P0-1 — widen decision-id-bearing columns to VARCHAR(64)
    # so canonical IDs like "dec:commercial_action:<hex12>" (34+ chars) persist.
    # These columns carry CompanyDecision.decision_id which can exceed 32 chars.
    
    # company_decision_precedents.precedent_decision_id
    op.alter_column(
        'company_decision_precedents',
        'precedent_decision_id',
        type_=sa.String(64),
        existing_type=sa.String(32),
        existing_nullable=False,
    )
    
    # company_decision_contradictions.precedent_decision_id
    op.alter_column(
        'company_decision_contradictions',
        'precedent_decision_id',
        type_=sa.String(64),
        existing_type=sa.String(32),
        existing_nullable=True,
    )
    
    # company_decision_contradictions.lesson_memory_id
    op.alter_column(
        'company_decision_contradictions',
        'lesson_memory_id',
        type_=sa.String(64),
        existing_type=sa.String(32),
        existing_nullable=True,
    )
    
    # knowledge_recommendations.decision_id
    op.alter_column(
        'knowledge_recommendations',
        'decision_id',
        type_=sa.String(64),
        existing_type=sa.String(32),
        existing_nullable=True,
    )


def downgrade() -> None:
    # Revert to VARCHAR(32) — note: will truncate data if any values > 32 chars
    op.alter_column(
        'knowledge_recommendations',
        'decision_id',
        type_=sa.String(32),
        existing_type=sa.String(64),
        existing_nullable=True,
    )
    
    op.alter_column(
        'company_decision_contradictions',
        'lesson_memory_id',
        type_=sa.String(32),
        existing_type=sa.String(64),
        existing_nullable=True,
    )
    
    op.alter_column(
        'company_decision_contradictions',
        'precedent_decision_id',
        type_=sa.String(32),
        existing_type=sa.String(64),
        existing_nullable=True,
    )
    
    op.alter_column(
        'company_decision_precedents',
        'precedent_decision_id',
        type_=sa.String(32),
        existing_type=sa.String(64),
        existing_nullable=False,
    )
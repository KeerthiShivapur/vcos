"""add supersedes_id to company_decision_contradictions

Revision ID: 001
Revises: 
Create Date: 2026-10-05
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Check if column exists before adding
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    
    if 'company_decision_contradictions' not in inspector.get_table_names(schema='public'):
        return
    
    columns = [col['name'] for col in sa.inspect(op.get_bind()).get_columns('company_decision_contradictions')]
    
    if 'supersedes_id' not in columns:
        op.add_column(
            'company_decision_contradictions',
            sa.Column('supersedes_id', sa.String(32), sa.ForeignKey('company_decision_contradictions.id', ondelete='SET NULL'), nullable=True)
        )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    
    if 'company_decision_contradictions' not in inspector.get_table_names(schema='public'):
        return
    
    columns = [col['name'] for col in sa.inspect(op.get_bind()).get_columns('company_decision_contradictions')]
    
    if 'supersedes_id' in columns:
        op.drop_column('company_decision_contradictions', 'supersedes_id')
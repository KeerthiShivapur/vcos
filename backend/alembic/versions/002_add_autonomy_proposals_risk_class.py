"""add risk_class to autonomy_proposals

Revision ID: 002
Revises: 001
Create Date: 2026-10-03
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ENUM


revision = '002'
down_revision = '001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Check if column exists before adding
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    
    # Check if table exists
    tables = inspector.get_table_names(schema='public')
    if 'autonomy_proposals' not in tables:
        # Table doesn't exist, skip
        return
    
    columns = [col['name'] for col in inspector.get_columns('autonomy_proposals', schema='public')]
    
    if 'risk_class' not in columns:
        # Create the enum type if it doesn't exist
        op.execute("""
            DO $$ BEGIN
                CREATE TYPE autonomy_risk_class AS ENUM (
                    'human_approval_required',
                    'auto_approved',
                    'conditional',
                    'restricted'
                );
            EXCEPTION WHEN duplicate_object THEN NULL;
            END $$;
        """)
        
        op.add_column(
            'autonomy_proposals',
            sa.Column('risk_class', sa.String(32), nullable=False, 
                      server_default='human_approval_required'),
            schema='public'
        )
        # Update existing rows to have a default value
        op.execute("UPDATE autonomy_proposals SET risk_class = 'human_approval_required' WHERE risk_class IS NULL")
        op.alter_column('autonomy_proposals', 'risk_class', server_default=None, schema='public')


def downgrade() -> None:
    # Check if column exists before dropping
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    
    tables = inspector.get_table_names(schema='public')
    if 'autonomy_proposals' not in tables:
        return
    
    columns = [col['name'] for col in inspector.get_columns('autonomy_proposals', schema='public')]
    
    if 'risk_class' in columns:
        op.drop_column('autonomy_proposals', 'risk_class', schema='public')


from alembic import op
import sqlalchemy as sa
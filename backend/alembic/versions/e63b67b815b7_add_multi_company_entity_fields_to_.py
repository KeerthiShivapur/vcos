"""Add multi-company entity fields to Organization

Revision ID: e63b67b815b7
Revises: 003
Create Date: 2026-10-05 12:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e63b67b815b7'
down_revision: Union[str, None] = '003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add multi-company entity fields to Organization table
    op.add_column('organizations', sa.Column('parent_organization_id', sa.String(32), nullable=True))
    op.add_column('organizations', sa.Column('entity_type', sa.String(24), nullable=False, server_default='standalone'))
    op.add_column('organizations', sa.Column('entity_code', sa.String(24), nullable=True))
    op.add_column('organizations', sa.Column('legal_name', sa.String(255), nullable=True))
    op.add_column('organizations', sa.Column('tax_id', sa.String(60), nullable=True))
    op.add_column('organizations', sa.Column('registration_number', sa.String(60), nullable=True))
    op.add_column('organizations', sa.Column('consolidation_method', sa.String(24), nullable=True))
    op.add_column('organizations', sa.Column('consolidation_percentage', sa.Integer(), nullable=True))
    op.add_column('organizations', sa.Column('functional_currency', sa.String(10), nullable=True))
    op.add_column('organizations', sa.Column('governance_scope', sa.String(32), nullable=True))
    op.add_column('organizations', sa.Column('management_structure_json', sa.JSON(), nullable=True))
    op.add_column('organizations', sa.Column('entity_mappings_json', sa.JSON(), nullable=True))
    op.add_column('organizations', sa.Column('attribute_mappings_json', sa.JSON(), nullable=True))
    
    # Create index on parent_organization_id
    op.create_index('ix_organizations_parent_organization_id', 'organizations', ['parent_organization_id'], unique=False)
    
    # Create index on entity_code
    op.create_index('ix_organizations_entity_code', 'organizations', ['entity_code'], unique=False)
    
    # Add foreign key constraint for parent_organization_id
    op.create_foreign_key(
        'fk_organizations_parent_organization_id',
        'organizations', 'organizations',
        ['parent_organization_id'], ['id'],
        ondelete='SET NULL'
    )


def downgrade() -> None:
    # Drop foreign key constraint
    op.drop_constraint('fk_organizations_parent_organization_id', 'organizations', type_='foreignkey')
    
    # Drop indexes
    op.drop_index('ix_organizations_parent_organization_id', table_name='organizations')
    op.drop_index('ix_organizations_entity_code', table_name='organizations')
    
    # Drop columns
    op.drop_column('organizations', 'attribute_mappings_json')
    op.drop_column('organizations', 'entity_mappings_json')
    op.drop_column('organizations', 'management_structure_json')
    op.drop_column('organizations', 'governance_scope')
    op.drop_column('organizations', 'functional_currency')
    op.drop_column('organizations', 'consolidation_percentage')
    op.drop_column('organizations', 'consolidation_method')
    op.drop_column('organizations', 'registration_number')
    op.drop_column('organizations', 'tax_id')
    op.drop_column('organizations', 'legal_name')
    op.drop_column('organizations', 'entity_code')
    op.drop_column('organizations', 'entity_type')
    op.drop_column('organizations', 'parent_organization_id')

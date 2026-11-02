"""add backup_manifests and related tables

Revision ID: 003
Revises: 002
Create Date: 2026-10-03
"""
from alembic import op
import sqlalchemy as sa
import uuid
from datetime import datetime, timezone


revision = '003'
down_revision = '002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create enum types (idempotent)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE backup_kind AS ENUM (
                'full', 'incremental', 'daily', 'weekly', 'monthly', 
                'on_demand', 'pre_deployment', 'post_deployment', 
                'pre_migration', 'post_migration'
            );
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)
    
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE backup_status AS ENUM (
                'pending', 'in_progress', 'completed', 'failed', 'verified',
                'failed_verification', 'expired', 'corrupted'
            );
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)

    # Check which tables exist
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = set(inspector.get_table_names(schema='public'))
    
    # backup_manifests table
    if 'backup_manifests' not in tables:
        op.create_table(
            'backup_manifests',
            sa.Column('id', sa.String(32), primary_key=True),
            sa.Column('organization_id', sa.String(32), 
                      sa.ForeignKey('organizations.id', ondelete='CASCADE'),
                      nullable=False, index=True),
            sa.Column('backup_kind', sa.String(20), nullable=False, default='full'),
            sa.Column('status', sa.String(24), nullable=False, default='pending', index=True),
            sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('database_url_hash', sa.String(64), nullable=True),
            sa.Column('pg_version', sa.String(32), nullable=True),
            sa.Column('schema_version', sa.String(32), nullable=True),
            sa.Column('vcos_version', sa.String(32), nullable=True),
            sa.Column('backup_format', sa.String(32), default='pgbackrest', nullable=False),
            sa.Column('backup_size_bytes', sa.BigInteger, default=0, nullable=False),
            sa.Column('checksum_sha256', sa.String(64), nullable=True),
            sa.Column('tables_included', sa.JSON, nullable=True),
            sa.Column('tables_excluded', sa.JSON, nullable=True),
            sa.Column('retention_days', sa.Integer, default=30, nullable=False),
            sa.Column('vault_bucket', sa.String(128), nullable=True),
            sa.Column('vault_path', sa.String(256), nullable=True),
            sa.Column('error', sa.Text, nullable=True),
            sa.Column('error_trace', sa.Text, nullable=True),
            sa.Column('last_verified_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('verification_status', sa.String(32), nullable=True),
            sa.Column('verification_details', sa.JSON, nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), 
                      server_default=sa.func.now(), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), 
                      server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
            sa.Column('version', sa.Integer, default=1, nullable=False),
            sa.Column('fingerprint', sa.String(160), nullable=True),
        )
        
        # Indexes
        op.create_index('ix_bkm_org_status', 'backup_manifests', ['organization_id', 'status'])
        op.create_index('ix_bkm_org_kind', 'backup_manifests', ['organization_id', 'backup_kind'])
        op.create_index('ix_bkm_org_scope', 'backup_manifests', ['organization_id', 'backup_kind', 'status'])
        op.create_index('ix_bkm_org_fingerprint', 'backup_manifests', ['organization_id', 'fingerprint'])
        
        # Create enum types (idempotent)
        op.execute("""
            DO $$ BEGIN
                CREATE TYPE backup_kind AS ENUM (
                    'full', 'incremental', 'daily', 'weekly', 'monthly', 
                    'on_demand', 'pre_deployment', 'post_deployment', 
                    'pre_migration', 'post_migration'
                );
            EXCEPTION WHEN duplicate_object THEN NULL;
            END $$;
        """)
        
        op.execute("""
            DO $$ BEGIN
                CREATE TYPE backup_status AS ENUM (
                    'pending', 'in_progress', 'completed', 'failed', 'verified',
                    'failed_verification', 'expired', 'corrupted'
                );
            EXCEPTION WHEN duplicate_object THEN NULL;
            END $$;
        """)
    else:
        # Table exists, check if indexes exist
        inspector = sa.inspect(op.get_bind())
        existing_indexes = set()
        for idx in inspector.get_indexes('backup_manifests', schema='public'):
            existing_indexes.add(idx['name'])
        
        if 'ix_bkm_org_status' not in existing_indexes:
            op.create_index('ix_bkm_org_status', 'backup_manifests', ['organization_id', 'status'])
        if 'ix_bkm_org_kind' not in existing_indexes:
            op.create_index('ix_bkm_org_kind', 'backup_manifests', ['organization_id', 'backup_kind'])
        if 'ix_bkm_org_scope' not in existing_indexes:
            op.create_index('ix_bkm_org_scope', 'backup_manifests', ['organization_id', 'backup_kind', 'status'])
        if 'ix_bkm_org_fingerprint' not in existing_indexes:
            op.create_index('ix_bkm_org_fingerprint', 'backup_manifests', ['organization_id', 'fingerprint'])

    # backup_verification_results table
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = set(inspector.get_table_names(schema='public'))
    
    if 'backup_verification_results' not in tables:
        op.create_table(
            'backup_verification_results',
            sa.Column('id', sa.String(32), primary_key=True),
            sa.Column('backup_id', sa.String(32), 
                      sa.ForeignKey('backup_manifests.id', ondelete='CASCADE'),
                      nullable=False, index=True),
            sa.Column('verified', sa.Boolean, default=False, nullable=False),
            sa.Column('verified_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('checksum_valid', sa.String(32), default='inconclusive', nullable=False),
            sa.Column('schema_valid', sa.String(32), default='inconclusive', nullable=False),
            sa.Column('data_integrity', sa.String(32), default='inconclusive', nullable=False),
            sa.Column('tenant_isolation', sa.String(32), default='inconclusive', nullable=False),
            sa.Column('temporal_integrity', sa.String(32), default='inconclusive', nullable=False),
            sa.Column('provenance_valid', sa.String(32), default='inconclusive', nullable=False),
            sa.Column('epistemic_valid', sa.String(32), default='inconclusive', nullable=False),
            sa.Column('governance_valid', sa.String(32), default='inconclusive', nullable=False),
            sa.Column('recovery_state_valid', sa.String(32), default='inconclusive', nullable=False),
            sa.Column('checks', sa.JSON, nullable=True),
            sa.Column('errors', sa.JSON, nullable=True),
            sa.Column('warnings', sa.JSON, nullable=True),
            sa.Column('validation_details', sa.JSON, nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), 
                      server_default=sa.func.now(), nullable=False),
            sa.Column('fingerprint', sa.String(160), nullable=True),
            sa.ForeignKeyConstraint(['backup_id'], ['backup_manifests.id'], ondelete='CASCADE'),
        )
        op.create_index('ix_bvr_backup', 'backup_verification_results', ['backup_id'])

    # restore_operations table
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = set(inspector.get_table_names(schema='public'))
    
    if 'restore_operations' not in tables:
        op.create_table(
            'restore_operations',
            sa.Column('id', sa.String(32), primary_key=True),
            sa.Column('backup_id', sa.String(32), 
                      sa.ForeignKey('backup_manifests.id', ondelete='CASCADE'),
                      nullable=False, index=True),
            sa.Column('organization_id', sa.String(32), 
                      sa.ForeignKey('organizations.id', ondelete='CASCADE'),
                      nullable=False, index=True),
            sa.Column('target_time', sa.DateTime(timezone=True), nullable=True),
            sa.Column('target_version', sa.Integer, nullable=True),
            sa.Column('initiated_by', sa.String(64), nullable=False),
            sa.Column('phase', sa.String(32), nullable=False, default='pending'),
            sa.Column('status', sa.String(24), nullable=False, default='in_progress'),
            sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('error', sa.Text, nullable=True),
            sa.Column('details', sa.JSON, nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), 
                      server_default=sa.func.now(), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), 
                      server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(['backup_id'], ['backup_manifests.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        )
        
        # Indexes
        op.create_index('ix_rop_org_phase', 'restore_operations', ['organization_id', 'phase'])
        op.create_index('ix_rop_org_status', 'restore_operations', ['organization_id', 'status'])
    
    # Create enum types (idempotent)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE backup_kind AS ENUM (
                'full', 'incremental', 'daily', 'weekly', 'monthly', 
                'on_demand', 'pre_deployment', 'post_deployment', 
                'pre_migration', 'post_migration'
            );
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)
    
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE backup_status AS ENUM (
                'pending', 'in_progress', 'completed', 'failed', 'verified',
                'failed_verification', 'expired', 'corrupted'
            );
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)


def downgrade() -> None:
    op.drop_index('ix_bvr_backup', table_name='backup_verification_results')
    op.drop_index('ix_rop_org_status', table_name='restore_operations')
    op.drop_index('ix_rop_org_phase', table_name='restore_operations')
    op.drop_index('ix_bkm_org_fingerprint', table_name='backup_manifests')
    op.drop_index('ix_bkm_org_scope', table_name='backup_manifests')
    op.drop_index('ix_bkm_org_kind', table_name='backup_manifests')
    op.drop_index('ix_bkm_org_status', table_name='backup_manifests')
    op.drop_table('restore_operations')
    op.drop_table('backup_verification_results')
    op.drop_table('backup_manifests')
    
    # Drop enum types
    op.execute("DROP TYPE IF EXISTS backup_kind")
    op.execute("DROP TYPE IF EXISTS backup_status")


from alembic import op
import sqlalchemy as sa
import uuid
from datetime import datetime, timezone
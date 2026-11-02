import asyncio
import sys
sys.path.insert(0, '.')
import os
os.environ['DATABASE_URL'] = 'postgresql+asyncpg://postgres:postgres@192.168.208.1:5432/vcos4'

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

async def create_tables():
    engine = create_async_engine('postgresql+asyncpg://postgres:postgres@192.168.208.1:5432/vcos4')
    async with engine.connect() as conn:
        # Create enum types
        await conn.execute(text("""
            DO $$ BEGIN
                CREATE TYPE backup_kind AS ENUM (
                    'full', 'incremental', 'daily', 'weekly', 'monthly', 
                    'on_demand', 'pre_deployment', 'post_deployment', 
                    'pre_migration', 'post_migration'
                );
            EXCEPTION WHEN duplicate_object THEN NULL;
            END $$;
        """))
        
        await conn.execute(text("""
            DO $$ BEGIN
                CREATE TYPE backup_status AS ENUM (
                    'pending', 'in_progress', 'completed', 'failed', 'verified',
                    'failed_verification', 'expired', 'corrupted'
                );
            EXCEPTION WHEN duplicate_object THEN NULL;
            END $$;
        """))
        
        # Create backup_manifests table
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS backup_manifests (
                id VARCHAR(32) PRIMARY KEY,
                organization_id VARCHAR(32) NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
                backup_kind backup_kind NOT NULL DEFAULT 'full',
                status backup_status NOT NULL DEFAULT 'pending',
                started_at TIMESTAMP WITH TIME ZONE NOT NULL,
                completed_at TIMESTAMP WITH TIME ZONE,
                expires_at TIMESTAMP WITH TIME ZONE,
                database_url_hash VARCHAR(64),
                pg_version VARCHAR(32),
                schema_version VARCHAR(32),
                vcos_version VARCHAR(32),
                backup_format VARCHAR(32) NOT NULL DEFAULT 'pgbackrest',
                backup_size_bytes BIGINT NOT NULL DEFAULT 0,
                checksum_sha256 VARCHAR(64),
                tables_included JSON,
                tables_excluded JSON,
                retention_days INTEGER NOT NULL DEFAULT 30,
                vault_bucket VARCHAR(128),
                vault_path VARCHAR(256),
                error TEXT,
                error_trace TEXT,
                last_verified_at TIMESTAMP WITH TIME ZONE,
                verification_status VARCHAR(32),
                verification_details JSON,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
                version INTEGER NOT NULL DEFAULT 1,
                fingerprint VARCHAR(160)
            )
        """))
        
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_bkm_org_status ON backup_manifests (organization_id, status)
        """))
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_bkm_org_kind ON backup_manifests (organization_id, backup_kind)
        """))
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_bkm_org_scope ON backup_manifests (organization_id, backup_kind, status)
        """))
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_bkm_org_fingerprint ON backup_manifests (organization_id, fingerprint)
        """))
        
        # Create backup_verification_results table
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS backup_verification_results (
                id VARCHAR(32) PRIMARY KEY,
                backup_id VARCHAR(32) NOT NULL REFERENCES backup_manifests(id) ON DELETE CASCADE,
                verified BOOLEAN NOT NULL DEFAULT FALSE,
                verified_at TIMESTAMP WITH TIME ZONE NOT NULL,
                checksum_valid VARCHAR(32) NOT NULL DEFAULT 'inconclusive',
                schema_valid VARCHAR(32) NOT NULL DEFAULT 'inconclusive',
                data_integrity VARCHAR(32) NOT NULL DEFAULT 'inconclusive',
                tenant_isolation VARCHAR(32) NOT NULL DEFAULT 'inconclusive',
                temporal_integrity VARCHAR(32) NOT NULL DEFAULT 'inconclusive',
                provenance_valid VARCHAR(32) NOT NULL DEFAULT 'inconclusive',
                epistemic_valid VARCHAR(32) NOT NULL DEFAULT 'inconclusive',
                governance_valid VARCHAR(32) NOT NULL DEFAULT 'inconclusive',
                recovery_state_valid VARCHAR(32) NOT NULL DEFAULT 'inconclusive',
                checks JSON,
                errors JSON,
                warnings JSON,
                validation_details JSON,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
                fingerprint VARCHAR(160)
            )
        """))
        
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_bvr_backup ON backup_verification_results (backup_id)
        """))
        
        # Create restore_operations table
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS restore_operations (
                id VARCHAR(32) PRIMARY KEY,
                backup_id VARCHAR(32) NOT NULL REFERENCES backup_manifests(id) ON DELETE CASCADE,
                organization_id VARCHAR(32) NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
                restore_id VARCHAR(32) NOT NULL UNIQUE,
                target_time TIMESTAMP WITH TIME ZONE,
                target_version INTEGER,
                initiated_by VARCHAR(64) NOT NULL,
                phase VARCHAR(64) NOT NULL DEFAULT 'pending',
                status VARCHAR(32) NOT NULL DEFAULT 'in_progress',
                started_at TIMESTAMP WITH TIME ZONE NOT NULL,
                completed_at TIMESTAMP WITH TIME ZONE,
                error TEXT,
                details JSON,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
                version INTEGER NOT NULL DEFAULT 1,
                fingerprint VARCHAR(160)
            )
        """))
        
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_rop_org_phase ON restore_operations (organization_id, phase)
        """))
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_rop_org_status ON restore_operations (organization_id, status)
        """))
        
        await conn.commit()
        print("Backup tables created successfully")

asyncio.run(create_tables())
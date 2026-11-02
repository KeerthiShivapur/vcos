import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

async def setup():
    engine = create_async_engine('postgresql+asyncpg://postgres@localhost:5432/vcos_test', isolation_level='AUTOCOMMIT')
    async with engine.connect() as conn:
        # Ensure vcos owns autonomy_proposals
        await conn.execute(text('ALTER TABLE autonomy_proposals OWNER TO vcos'))
        print('Changed autonomy_proposals owner to vcos')
        
        # Add risk_class column
        await conn.execute(text("""
            ALTER TABLE autonomy_proposals 
            ADD COLUMN IF NOT EXISTS risk_class VARCHAR(50) 
            DEFAULT 'human_approval_required'
        """))
        print('Added risk_class column')
        
        # Create backup_kind enum type
        await conn.execute(text("""
            DO $$ BEGIN
                CREATE TYPE backup_kind AS ENUM ('full', 'incremental', 'differential', 'snapshot');
            EXCEPTION WHEN duplicate_object THEN NULL;
            END $$;
        """))
        print('Created backup_kind enum')
        
        # Create backup_status enum type
        await conn.execute(text("""
            DO $$ BEGIN
                CREATE TYPE backup_status AS ENUM ('pending', 'running', 'completed', 'failed', 'corrupted');
            EXCEPTION WHEN duplicate_object THEN NULL;
            END $$;
        """))
        print('Created backup_status enum')
        
        # Create backup_manifests table
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS backup_manifests (
                id VARCHAR(32) PRIMARY KEY,
                organization_id VARCHAR(32) NOT NULL,
                backup_kind backup_kind NOT NULL,
                status backup_status NOT NULL DEFAULT 'pending',
                started_at TIMESTAMP WITH TIME ZONE NOT NULL,
                completed_at TIMESTAMP WITH TIME ZONE,
                size_bytes BIGINT,
                checksum VARCHAR(128),
                storage_path VARCHAR(512) NOT NULL,
                metadata_json JSONB DEFAULT '{}',
                error_message TEXT,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )
        """))
        print('Created backup_manifests table')
        
        # Change owner to vcos
        await conn.execute(text('ALTER TABLE backup_manifests OWNER TO vcos'))
        print('Changed backup_manifests owner to vcos')
        
        # Create indexes for backup_manifests
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_bkm_org_kind ON backup_manifests (organization_id, backup_kind)
        """))
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_bkm_org_status ON backup_manifests (organization_id, status)
        """))
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_bkm_started_at ON backup_manifests (started_at)
        """))
        print('Created backup_manifests indexes')
        
        # Create backup_verification_results table
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS backup_verification_results (
                id VARCHAR(32) PRIMARY KEY,
                manifest_id VARCHAR(32) NOT NULL REFERENCES backup_manifests(id) ON DELETE CASCADE,
                verified_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                verified_by VARCHAR(32),
                is_valid BOOLEAN NOT NULL,
                details_json JSONB DEFAULT '{}',
                checksum_match BOOLEAN,
                size_match BOOLEAN,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )
        """))
        print('Created backup_verification_results table')
        
        await conn.execute(text('ALTER TABLE backup_verification_results OWNER TO vcos'))
        print('Changed backup_verification_results owner to vcos')
        
        # Create indexes for backup_verification_results
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_bvr_manifest_id ON backup_verification_results (manifest_id)
        """))
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_bvr_verified_at ON backup_verification_results (verified_at)
        """))
        print('Created backup_verification_results indexes')
        
        # Create restore_operations table
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS restore_operations (
                id VARCHAR(32) PRIMARY KEY,
                organization_id VARCHAR(32) NOT NULL,
                manifest_id VARCHAR(32) NOT NULL REFERENCES backup_manifests(id) ON DELETE CASCADE,
                target_database VARCHAR(256) NOT NULL,
                phase VARCHAR(50) NOT NULL DEFAULT 'pending',
                started_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                completed_at TIMESTAMP WITH TIME ZONE,
                status VARCHAR(50) NOT NULL DEFAULT 'pending',
                progress_pct REAL DEFAULT 0.0,
                error_message TEXT,
                metadata_json JSONB DEFAULT '{}',
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )
        """))
        print('Created restore_operations table')
        
        await conn.execute(text('ALTER TABLE restore_operations OWNER TO vcos'))
        print('Changed restore_operations owner to vcos')
        
        # Create indexes for restore_operations
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_rop_org_manifest ON restore_operations (organization_id, manifest_id)
        """))
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_rop_status ON restore_operations (status)
        """))
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_rop_started_at ON restore_operations (started_at)
        """))
        print('Created restore_operations indexes')
        
        # Verify all tables
        result = await conn.execute(text("""
            SELECT tablename, tableowner 
            FROM pg_tables 
            WHERE tablename IN ('autonomy_proposals', 'backup_manifests', 'backup_verification_results', 'restore_operations')
        """))
        print('Final table owners:', result.fetchall())
        
        result = await conn.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'autonomy_proposals' AND column_name = 'risk_class'
        """))
        print('risk_class column exists:', bool(result.fetchall()))
    
    await engine.dispose()
    print('Schema setup complete!')

asyncio.run(setup())
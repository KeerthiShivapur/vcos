import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from app.db.database import Base
from app import models  # noqa: F401

async def setup():
    # Use postgres user with autocommit to have full control
    engine = create_async_engine('postgresql+asyncpg://postgres@localhost:5432/vcos_test', isolation_level='AUTOCOMMIT')
    
    async with engine.connect() as conn:
        # Drop existing backup tables (they have wrong schema)
        await conn.execute(text('DROP TABLE IF EXISTS backup_corruption_tests CASCADE'))
        await conn.execute(text('DROP TABLE IF EXISTS restore_operations CASCADE'))
        await conn.execute(text('DROP TABLE IF EXISTS backup_verification_results CASCADE'))
        await conn.execute(text('DROP TABLE IF EXISTS backup_manifests CASCADE'))
        print('Dropped existing backup tables')
        
        # Drop enum types
        await conn.execute(text('DROP TYPE IF EXISTS backupkind CASCADE'))
        await conn.execute(text('DROP TYPE IF EXISTS backupstatus CASCADE'))
        await conn.execute(text('DROP TYPE IF EXISTS backup_kind CASCADE'))
        await conn.execute(text('DROP TYPE IF EXISTS backup_status CASCADE'))
        print('Dropped enum types')
    
    # Now create all tables using SQLAlchemy metadata (this will use the correct schema from models)
    # But we need to run this as postgres to have ownership
    # We'll use the sync engine for create_all since it's simpler
    from sqlalchemy import create_engine
    sync_engine = create_engine('postgresql+psycopg2://postgres@localhost:5432/vcos_test', isolation_level='AUTOCOMMIT')
    
    # Create only the backup-related tables
    from app.models.backup_manifest import BackupManifest, BackupVerificationResult, RestoreOperation, BackupCorruptionTest
    
    # Create tables
    Base.metadata.create_all(sync_engine, tables=[
        BackupManifest.__table__,
        BackupVerificationResult.__table__,
        RestoreOperation.__table__,
        BackupCorruptionTest.__table__,
    ])
    print('Created backup tables with correct schema')
    
    # Change ownership to vcos
    async with engine.connect() as conn:
        await conn.execute(text('ALTER TABLE backup_manifests OWNER TO vcos'))
        await conn.execute(text('ALTER TABLE backup_verification_results OWNER TO vcos'))
        await conn.execute(text('ALTER TABLE restore_operations OWNER TO vcos'))
        await conn.execute(text('ALTER TABLE backup_corruption_tests OWNER TO vcos'))
        print('Changed table ownership to vcos')
        
        # Verify
        result = await conn.execute(text("""
            SELECT tablename, tableowner 
            FROM pg_tables 
            WHERE tablename IN ('backup_manifests', 'backup_verification_results', 'restore_operations', 'backup_corruption_tests')
        """))
        print('Table owners:', result.fetchall())
    
    await engine.dispose()
    sync_engine.dispose()
    print('Schema recreation complete!')

asyncio.run(setup())
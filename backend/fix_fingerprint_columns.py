import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

async def setup():
    engine = create_async_engine('postgresql+asyncpg://postgres@localhost:5432/vcos_test', isolation_level='AUTOCOMMIT')
    async with engine.connect() as conn:
        # Add fingerprint column to backup_manifests if missing
        await conn.execute(text("""
            ALTER TABLE backup_manifests 
            ADD COLUMN IF NOT EXISTS fingerprint VARCHAR(160)
        """))
        print('Added fingerprint column to backup_manifests')
        
        # Add fingerprint column to backup_verification_results if missing
        await conn.execute(text("""
            ALTER TABLE backup_verification_results 
            ADD COLUMN IF NOT EXISTS fingerprint VARCHAR(160)
        """))
        print('Added fingerprint column to backup_verification_results')
        
        # Add fingerprint column to restore_operations if missing
        await conn.execute(text("""
            ALTER TABLE restore_operations 
            ADD COLUMN IF NOT EXISTS fingerprint VARCHAR(160)
        """))
        print('Added fingerprint column to restore_operations')
        
        # Verify columns
        result = await conn.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'backup_manifests' AND column_name = 'fingerprint'
        """))
        print('backup_manifests fingerprint exists:', bool(result.fetchall()))
        
        result = await conn.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'backup_verification_results' AND column_name = 'fingerprint'
        """))
        print('backup_verification_results fingerprint exists:', bool(result.fetchall()))
        
        result = await conn.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'restore_operations' AND column_name = 'fingerprint'
        """))
        print('restore_operations fingerprint exists:', bool(result.fetchall()))
    
    await engine.dispose()
    print('Schema fix complete!')

asyncio.run(setup())
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

async def check():
    engine = create_async_engine('postgresql+asyncpg://vcos:vcos@localhost:5432/vcos_test')
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT table_name FROM information_schema.tables WHERE table_name IN ('backup_manifests', 'backup_verification_results', 'restore_operations')"))
        print('Backup-related tables:', result.fetchall())
        
        # Check indexes
        result = await conn.execute(text("SELECT indexname FROM pg_indexes WHERE tablename = 'backup_manifests'"))
        print('backup_manifests indexes:', result.fetchall())

asyncio.run(check())
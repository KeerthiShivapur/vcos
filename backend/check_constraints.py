import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

async def check():
    engine = create_async_engine('postgresql+asyncpg://vcos:vcos@localhost:5432/vcos_test')
    async with engine.connect() as conn:
        # Check constraints
        result = await conn.execute(text("SELECT conname, conrelid::regclass as table_name FROM pg_constraint WHERE conname = 'fk_backup_verification_results_backup_id_backup_manifests'"))
        print('Constraint:', result.fetchall())
        
        # Check all constraints on backup_verification_results if it exists
        result = await conn.execute(text("SELECT conname, contype, conrelid::regclass as table_name FROM pg_constraint WHERE conrelid = 'backup_verification_results'::regclass"))
        print('Constraints on backup_verification_results:', result.fetchall())

asyncio.run(check())
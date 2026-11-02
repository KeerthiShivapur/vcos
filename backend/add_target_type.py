import asyncio
import os
os.environ['DATABASE_URL'] = 'postgresql+asyncpg://postgres:postgres@localhost:5432/vcos_test'

async def add_target_type():
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy import text
    engine = create_async_engine('postgresql+asyncpg://postgres:postgres@localhost:5432/vcos_test')
    async with engine.begin() as conn:
        # Check if target_type column exists
        result = await conn.execute(text('''
            SELECT column_name FROM information_schema.columns 
            WHERE table_name = 'canonical_operations' AND column_name = 'target_type'
        '''))
        if not result.fetchone():
            await conn.execute(text('ALTER TABLE canonical_operations ADD COLUMN target_type VARCHAR(100)'))
            print('Added target_type column')
        else:
            print('target_type column already exists')
    await engine.dispose()

asyncio.run(add_target_type())
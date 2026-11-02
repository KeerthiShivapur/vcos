import asyncio
import os
os.environ['DATABASE_URL'] = 'postgresql+asyncpg://postgres:postgres@localhost:5432/vcos_test'

async def check_table():
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy import text
    engine = create_async_engine('postgresql+asyncpg://postgres:postgres@localhost:5432/vcos_test')
    async with engine.begin() as conn:
        result = await conn.execute(text("SELECT table_name FROM information_schema.tables WHERE table_name = 'schema_migrations'"))
        row = result.fetchone()
        print('schema_migrations exists:', row is not None)
        
        # Also test the query
        try:
            result = await conn.execute(text("SELECT version FROM schema_migrations ORDER BY version DESC LIMIT 1"))
            print('Query result:', result.scalar())
        except Exception as e:
            print('Query error:', e)
    await engine.dispose()

asyncio.run(check_table())
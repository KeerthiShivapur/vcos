import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

async def cleanup():
    engine = create_async_engine('postgresql+asyncpg://postgres:postgres@localhost:5432/vcos_test', poolclass=None)
    async with engine.begin() as conn:
        await conn.execute(text("""
            SELECT pg_terminate_backend(pid) 
            FROM pg_stat_activity 
            WHERE datname = 'vcos_test' 
            AND pid <> pg_backend_pid()
        """))
        print('Terminated connections')
    await engine.dispose()

asyncio.run(cleanup())
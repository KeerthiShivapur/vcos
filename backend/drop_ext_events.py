import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

async def drop_table():
    engine = create_async_engine('postgresql+asyncpg://postgres:postgres@localhost:5432/vcos_test', poolclass=None)
    async with engine.begin() as conn:
        await conn.execute(text('DROP TABLE IF EXISTS external_events CASCADE'))
    await engine.dispose()
    print('Table dropped')

asyncio.run(drop_table())
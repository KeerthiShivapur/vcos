import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

async def create_ext():
    engine = create_async_engine('postgresql+asyncpg://postgres:postgres@localhost:5432/vcos')
    async with engine.begin() as conn:
        await conn.execute(text('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"'))
        await conn.execute(text('CREATE EXTENSION IF NOT EXISTS btree_gin'))
        await conn.execute(text('CREATE EXTENSION IF NOT EXISTS btree_gist'))
    print('Extensions created')

asyncio.run(create_ext())
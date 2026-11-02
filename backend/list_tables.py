import asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

async def test():
    url = 'postgresql+asyncpg://vcos:vcos@localhost:5432/vcos_test'
    engine = create_async_engine(url, poolclass=NullPool)
    async with engine.begin() as conn:
        result = await conn.execute(text("""
            SELECT table_name FROM information_schema.tables 
            WHERE table_schema = 'public'
            ORDER BY table_name
        """))
        tables = [row[0] for row in result.fetchall()]
        for t in tables:
            print(t)

asyncio.run(test())
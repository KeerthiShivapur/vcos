import asyncio
import sys
sys.path.insert(0, '.')
import os
os.environ['DATABASE_URL'] = 'postgresql+asyncpg://postgres:postgres@192.168.208.1:5432/vcos4'

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

async def test():
    engine = create_async_engine('postgresql+asyncpg://postgres:postgres@192.168.208.1:5432/vcos4')
    async with engine.connect() as conn:
        # Try to use the enum in a query
        result = await conn.execute(text("SELECT 'full'::backup_kind"))
        print('Enum cast works:', result.scalar())
        
        # Try to create a table with the enum
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS test_enum (
                id SERIAL PRIMARY KEY,
                kind backup_kind NOT NULL
            )
        """))
        await conn.execute(text("INSERT INTO test_enum (kind) VALUES ('full')"))
        result = await conn.execute(text("SELECT * FROM test_enum"))
        for row in result:
            print('Row:', row)
        await conn.execute(text("DROP TABLE test_enum"))

asyncio.run(test())
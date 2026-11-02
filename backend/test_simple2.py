import os
os.environ['TEST_DATABASE_URL'] = 'postgresql+asyncpg://postgres:postgres@localhost:5432/vcos_test'
os.environ['PATH'] += ';C:\\Program Files\\PostgreSQL\\18\\bin'

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import text
import asyncio
import time

async def test():
    print("Creating engine...")
    start = time.time()
    engine = create_async_engine(
        'postgresql+asyncpg://postgres:postgres@localhost:5432/vcos_test',
        pool_size=1,
        max_overflow=0,
        pool_pre_ping=True,
        connect_args={"server_settings": {"search_path": "public"}},
        echo=False,
        future=True,
    )
    print(f"Engine created in {time.time() - start:.2f}s")
    
    session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    
    print("Testing connection...")
    async with engine.begin() as conn:
        result = await conn.execute(text("SELECT 1"))
        print(f"SELECT 1: {result.scalar()}")
    
    print("Testing schema privileges...")
    async with engine.begin() as conn:
        result = await conn.execute(text("SELECT current_schema()"))
        schema = result.scalar() or "unknown"
        print(f"Schema: {schema}")
        
        await conn.execute(text("CREATE TEMP TABLE _readiness_priv_test (id INT)"))
        await conn.execute(text("DROP TABLE _readiness_priv_test"))
        print("Temp table test passed")
        
        try:
            await conn.execute(text("CREATE SCHEMA _readiness_schema_test"))
            await conn.execute(text("DROP SCHEMA _readiness_schema_test"))
            print("Schema create/drop test passed")
        except Exception as e:
            print(f"Schema test failed: {e}")
    
    print("Testing write capability...")
    async with engine.begin() as conn:
        await conn.execute(text("CREATE TEMP TABLE _readiness_write_test (id INT, data TEXT)"))
        await conn.execute(text("INSERT INTO _readiness_write_test VALUES (1, 'test')"))
        await conn.execute(text("UPDATE _readiness_write_test SET data = 'updated' WHERE id = 1"))
        await conn.execute(text("DELETE FROM _readiness_write_test WHERE id = 1"))
        await conn.execute(text("DROP TABLE _readiness_write_test"))
        print("Write capability test passed")
    
    await engine.dispose()

import asyncio
import time
asyncio.run(test())
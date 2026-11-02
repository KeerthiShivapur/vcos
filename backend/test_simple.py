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
    
    print("Creating session factory...")
    session_factory = async_sessionmaker(
        engine,
        class_=asyncio,  # This is wrong, should be AsyncSession
        expire_on_commit=False,
    )
    
    print("Testing connection...")
    async with engine.begin() as conn:
        result = await conn.execute(text("SELECT 1"))
        print(f"SELECT 1: {result.scalar()}")
    
    print("Testing SELECT current_user...")
    async with engine.begin() as conn:
        result = await conn.execute(text("SELECT current_user, current_database()"))
        row = result.first()
        if row:
            print(f"User: {row[0]}, Database: {row[1]}")
    
    await engine.dispose()

import asyncio
import time
asyncio.run(test())
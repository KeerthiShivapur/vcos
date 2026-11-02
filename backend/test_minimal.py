import os
os.environ['TEST_DATABASE_URL'] = 'postgresql+asyncpg://postgres:postgres@localhost:5432/vcos_test'
os.environ['PATH'] += ';C:\\Program Files\\PostgreSQL\\18\\bin'

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import text
import asyncio
import time
import sys

def log(msg):
    print(msg, flush=True)
    sys.stdout.flush()

async def test():
    log("Step 1: Creating engine...")
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
    log(f"Engine created in {time.time() - start:.2f}s")
    
    log("Creating session factory...")
    session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    log("Session factory created")
    
    log("Testing engine...")
    start = time.time()
    async with engine.begin() as conn:
        result = await conn.execute(text("SELECT 1"))
        log(f"SELECT 1: {result.scalar()}")
    log(f"Query executed in {time.time() - start:.2f}s")
    
    log("Done")

import asyncio
import time
import sys
asyncio.run(test())
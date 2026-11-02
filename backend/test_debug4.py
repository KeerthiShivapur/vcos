import os
os.environ['TEST_DATABASE_URL'] = 'postgresql+asyncpg://postgres:postgres@localhost:5432/vcos_test'
os.environ['PATH'] += ';C:\\Program Files\\PostgreSQL\\18\\bin'

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import text
import asyncio
import time

async def test():
    print("Step 1: Creating engine...")
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
    
    print("Step 2: Creating session factory...")
    session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    print("Session factory created")
    
    print("Step 3: Testing engine...")
    start = time.time()
    async with engine.begin() as conn:
        result = await conn.execute(text("SELECT 1"))
        print(f"SELECT 1: {result.scalar()}")
    print(f"Query executed in {time.time() - start:.2f}s")
    
    print("Step 2: Creating session factory...")
    session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    print("Session factory created")
    
    print("Step 3: Testing session factory...")
    start = time.time()
    async with session_factory() as session:
        result = await session.execute(text("SELECT 1"))
        print(f"Session query: {result.scalar()}")
    print(f"Session query in {time.time() - start:.2f}s")
    
    print("Step 4: Creating assessor engine...")
    from tests.scale.readiness import ScaleEnvironmentReadinessAssessor
    assessor = ScaleEnvironmentReadinessAssessor('postgresql+asyncpg://postgres:postgres@localhost:5432/vcos_test', 'localhost:5432/vcos_test')
    print("Assessor created")
    
    print("Step 5: Creating engine in assessor...")
    start = time.time()
    assessor._engine = create_async_engine(
        assessor.db_url,
        pool_size=1,
        max_overflow=0,
        pool_pre_ping=True,
        connect_args={"server_settings": {"search_path": "public"}},
        echo=False,
        future=True,
    )
    print("Engine created in assessor")
    
    start = time.time()
    assessor._session_factory = async_sessionmaker(
        assessor._engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    print(f"Assessor initialized in {time.time() - start:.2f}s")
    
    print("About to call assessor.assess()...")
    start = time.time()
    result = await assessor.assess()
    print(f"Assessed in {time.time() - start:.2f}s")
    print(f"State: {result.state.value}")

import asyncio
import time
asyncio.run(test())
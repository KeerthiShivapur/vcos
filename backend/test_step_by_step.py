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
    log("Step 1: Creating assessor...")
    from tests.scale.readiness import ScaleEnvironmentReadinessAssessor
    assessor = ScaleEnvironmentReadinessAssessor('postgresql+asyncpg://postgres:postgres@localhost:5432/vcos_test', 'localhost:5432/vcos_test')
    log("Assessor created")
    
    log("Step 2: Calling initialize()...")
    start = time.time()
    log("About to create engine in assessor...")
    assessor._engine = create_async_engine(
        assessor.db_url,
        pool_size=1,
        max_overflow=0,
        pool_pre_ping=True,
        connect_args={"server_settings": {"search_path": "public"}},
        echo=False,
        future=True,
    )
    log("Engine created in assessor")
    
    log("Creating session factory...")
    assessor._session_factory = async_sessionmaker(
        assessor._engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    log(f"Assessor initialized in {time.time() - start:.2f}s")
    
    log("About to call assessor.assess()...")
    start = time.time()
    result = await assessor.assess()
    log(f"Assessed in {time.time() - start:.2f}s")
    log(f"State: {result.state.value}")

import asyncio
import time
import sys
asyncio.run(test())
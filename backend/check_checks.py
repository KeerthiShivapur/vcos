import os
os.environ['TEST_DATABASE_URL'] = 'postgresql+asyncpg://postgres:postgres@localhost:5432/vcos_test'
os.environ['PATH'] += ';C:\\Program Files\\PostgreSQL\\18\\bin'

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import text
from tests.scale.readiness import ScaleEnvironmentReadinessAssessor, ReadinessCheck
import asyncio
import time
import sys

def log(msg):
    print(msg, flush=True)
    sys.stdout.flush()

async def test():
    log("Step 1: Creating assessor...")
    assessor = ScaleEnvironmentReadinessAssessor('postgresql+asyncpg://postgres:postgres@localhost:5432/vcos_test', 'localhost:5432/vcos_test')
    log("Assessor created")
    
    log("Step 2: Calling initialize()...")
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
    log("Engine created in assessor")
    
    assessor._session_factory = async_sessionmaker(
        assessor._engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    log(f"Assessor initialized in {time.time() - start:.2f}s")
    
    log("About to call assessor.assess()...")
    start = time.time()
    
    # Manually run each check to see which one hangs
    readiness_checks = [
        (ReadinessCheck.REACHABLE, "_check_reachable"),
        (ReadinessCheck.AUTHENTICATED, "_check_authenticated"),
        (ReadinessCheck.VERSION_SUPPORTED, "_check_version"),
        (ReadinessCheck.EXTENSIONS_AVAILABLE, "_check_extensions"),
        (ReadinessCheck.SCHEMA_PRIVILEGES, "_check_schema_privileges"),
        (ReadinessCheck.WRITE_CAPABILITY, "_check_write_capability"),
        (ReadinessCheck.TRANSACTION_CAPABILITY, "_check_transaction_capability"),
        (ReadinessCheck.COPY_CAPABILITY, "_check_copy_capability"),
        (ReadinessCheck.CONNECTION_CAPACITY, "_check_connection_capacity"),
        (ReadinessCheck.CONNECTION_UTILIZATION, "_check_connection_utilization"),
        (ReadinessCheck.STORAGE_INFORMATION, "_check_storage_information"),
        (ReadinessCheck.DATABASE_SIZE, "_check_database_size"),
        (ReadinessCheck.RELEVANT_SETTINGS, "_check_relevant_settings"),
        (ReadinessCheck.SAFE_ISOLATION, "_check_safe_isolation"),
        (ReadinessCheck.EXPLICIT_AUTHORIZATION, "_check_explicit_authorization"),
        (ReadinessCheck.INDEX_CAPABILITY, "_check_index_capability"),
    ]
    
    for check, method_name in readiness_checks:
        log(f"Running check: {check.value} ({method_name})...")
        start = time.time()
        method = getattr(assessor, method_name)
        try:
            result = await method()
            log(f"  {check.value}: {'PASS' if result.passed else 'FAIL'} in {time.time() - start:.2f}s - {result.details}")
        except Exception as e:
            log(f"  {check.value}: ERROR - {e}")
    
    log("All checks completed")

import asyncio
import time
import sys
asyncio.run(test())
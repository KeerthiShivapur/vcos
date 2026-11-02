import os
os.environ['TEST_DATABASE_URL'] = 'postgresql+asyncpg://postgres:postgres@localhost:5432/vcos_test'
os.environ['PATH'] += ';C:\\Program Files\\PostgreSQL\\18\\bin'

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import text
import asyncio
import time

async def test():
    print("Creating engine...")
    engine = create_async_engine(
        'postgresql+asyncpg://postgres:postgres@localhost:5432/vcos_test',
        pool_size=1,
        max_overflow=0,
        pool_pre_ping=True,
        connect_args={"server_settings": {"search_path": "public"}},
        echo=False,
        future=True,
    )
    print("Engine created")
    
    session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    
    print("Testing transaction capability...")
    async with engine.begin() as conn:
        await conn.execute(text("BEGIN"))
        await conn.execute(text("SELECT 1"))
        await conn.execute(text("COMMIT"))
        print("Transaction test passed")
        
        await conn.execute(text("BEGIN"))
        await conn.execute(text("SELECT 1"))
        await conn.execute(text("ROLLBACK"))
        print("Rollback test passed")
    
    print("Testing copy capability...")
    async with engine.begin() as conn:
        await conn.execute(text("CREATE TEMP TABLE _readiness_copy_test (id INT, data TEXT)"))
        await conn.execute(text("COPY _readiness_copy_test FROM STDIN WITH (FORMAT CSV)"))
        print("Copy capability test passed")
    
    print("Testing connection capacity...")
    async with engine.begin() as conn:
        result = await conn.execute(text("""
            SELECT 
                setting::int as max_conn,
                (SELECT count(*) FROM pg_stat_activity) as used_conn
            FROM pg_settings WHERE name = 'max_connections'
        """))
        row = result.first()
        if row:
            max_conn, used_conn = row[0], row[1]
            available = max_conn - used_conn
            sufficient = available >= 20
            print(f"Max: {max_conn}, Used: {row[1]}, Available: {available}, Sufficient: {sufficient}")
    
    print("Testing connection utilization...")
    async with engine.begin() as conn:
        result = await conn.execute(text("""
            SELECT 
                setting::int as max_conn,
                (SELECT count(*) FROM pg_stat_activity) as used_conn
            FROM pg_settings WHERE name = 'max_connections'
        """))
        row = result.first()
        if row:
            max_conn, used_conn = row[0], row[1]
            utilization = used_conn / max_conn if max_conn > 0 else 0
            acceptable = utilization <= 0.7
            print(f"Utilization: {utilization:.1%}, Acceptable: {acceptable}")
    
    print("Testing storage information...")
    async with engine.begin() as conn:
        result = await conn.execute(text("SELECT pg_database_size(current_database()) as db_size"))
        size_bytes = result.scalar() or 0
        size_mb = size_bytes / (1024 * 1024)
        print(f"Database size: {size_mb:.2f} MB")
    
    print("Testing database size...")
    async with engine.begin() as conn:
        result = await conn.execute(text("SELECT pg_database_size(current_database()) as db_size"))
        size_bytes = result.scalar() or 0
        size_mb = size_bytes / (1024 * 1024)
        print(f"Database size: {size_mb:.2f} MB")
    
    print("Testing relevant settings...")
    async with engine.begin() as conn:
        result = await conn.execute(text("""
            SELECT name, setting FROM pg_settings 
            WHERE name IN (
                'shared_buffers', 'work_mem', 'maintenance_work_mem',
                'max_wal_size', 'checkpoint_timeout', 'effective_cache_size',
                'max_connections', 'max_parallel_workers_per_gather',
                'autovacuum', 'autovacuum_max_workers'
            )
            ORDER BY name
        """))
        settings = {row[0]: row[1] for row in result}
        print(f"Settings: {len(settings)} found")
    
    print("Testing safe isolation...")
    async with engine.begin() as conn:
        can_create_schema = False
        try:
            await conn.execute(text("CREATE SCHEMA _isolation_test"))
            await conn.execute(text("DROP SCHEMA _isolation_test"))
            can_create_schema = True
        except Exception:
            pass
        
        result = await conn.execute(text("SELECT current_database()"))
        db_name = result.scalar() or "unknown"
        is_test_db = "vcos_scale" in db_name.lower() or "test" in db_name.lower()
        print(f"Can create schema: {can_create_schema}, DB: {db_name}, Is test: {is_test_db}")
    
    print("Testing explicit authorization...")
    async with engine.begin() as conn:
        result = await conn.execute(text("SELECT current_database()"))
        db_name = result.scalar() or "unknown"
        prod_indicators = ["prod", "production", "live", "main", "primary"]
        is_likely_production = any(ind in db_name.lower() for ind in prod_indicators)
        print(f"DB: {db_name}, Is production: {is_likely_production}")
    
    print("Testing index capability...")
    async with engine.begin() as conn:
        await conn.execute(text("CREATE TEMP TABLE _readiness_index_test (id INT, data TEXT)"))
        await conn.execute(text("CREATE INDEX _readiness_idx_test ON _readiness_index_test (id)"))
        await conn.execute(text("DROP TABLE _readiness_index_test"))
        print("Index capability test passed")
    
    print("Testing copy capability...")
    async with engine.begin() as conn:
        await conn.execute(text("CREATE TEMP TABLE _readiness_copy_test (id INT, data TEXT)"))
        await conn.execute(text("COPY _readiness_copy_test FROM STDIN WITH (FORMAT CSV)"))
        print("Copy capability test passed")

import asyncio
asyncio.run(test())
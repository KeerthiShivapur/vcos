import asyncio
import os
import sys
sys.path.insert(0, r'D:\vcos1\workspace\vcos\backend')

os.environ['DATABASE_URL'] = 'postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/vcos4'
os.environ['VAULT_BUCKET'] = r'C:\VCOS-Backups'
os.environ['WAL_ARCHIVE_DIR'] = r'C:\VCOS-Backups\wal_archive'
os.environ.pop('VCOS_TEST_MODE', None)

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

async def test():
    engine = create_async_engine(
        'postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/vcos4',
        echo=False,
        future=True,
    )
    SessionLocal = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    async with SessionLocal() as db:
        # Check if RLS is enabled
        from sqlalchemy import text
        result = await db.execute(text("""
            SELECT COUNT(*) FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public' AND c.relrowsecurity = true AND c.relforcerowsecurity = true
        """))
        rls_count = result.scalar()
        print(f'Tables with FORCE RLS: {rls_count}')
        
        # Check current_organization_id function
        result = await db.execute(text("""
            SELECT prosrc FROM pg_proc 
            WHERE proname = 'current_organization_id' AND pronamespace = 'public'::regnamespace
        """))
        func = result.fetchone()
        if func:
            print('current_organization_id function exists')
            print(func[0][:100])
        else:
            print('current_organization_id function NOT FOUND')
        
        # Test setting context and querying
        await db.execute(text("SET ROLE vcos"))
        await db.execute(text("SELECT set_config('app.current_organization_id', 'test-org', false)"))
        result = await db.execute(text("SELECT current_organization_id()"))
        print(f'current_organization_id(): {result.scalar()}')
        
        # Create a test table and insert
        await db.execute(text("""
            CREATE TABLE IF NOT EXISTS test_rls (
                id TEXT PRIMARY KEY,
                organization_id TEXT NOT NULL,
                data TEXT
            )
        """))
        await db.execute(text("""
            ALTER TABLE test_rls ENABLE ROW LEVEL SECURITY
        """))
        await db.execute(text("""
            ALTER TABLE test_rls FORCE ROW LEVEL SECURITY
        """))
        await db.execute(text("""
            CREATE POLICY test_rls_select ON test_rls FOR SELECT USING (organization_id = current_organization_id())
        """))
        await db.execute(text("""
            CREATE POLICY test_rls_insert ON test_rls FOR INSERT WITH CHECK (organization_id = current_organization_id())
        """))
        
        # Insert with context
        await db.execute(text("""
            INSERT INTO test_rls (id, organization_id, data) VALUES ('test-1', 'test-org', 'test data')
        """))
        await db.commit()
        
        # Query with context
        result = await db.execute(text("SELECT * FROM test_rls"))
        rows = result.fetchall()
        print(f'Rows with context: {len(rows)}')
        
        # Clear context and query
        await db.execute(text("SELECT set_config('app.current_organization_id', '', false)"))
        await db.commit()
        
        result = await db.execute(text("SELECT * FROM test_rls"))
        rows = result.fetchall()
        print(f'Rows without context: {len(rows)}')
        
        # Cleanup
        await db.execute(text("DROP TABLE test_rls"))
        await db.commit()

asyncio.run(test())
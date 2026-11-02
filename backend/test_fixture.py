import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool
from sqlalchemy import text
from app.db.database import Base

# Import models first so Base is populated
from app import models  # noqa: F401

async def test_fixture():
    engine = create_async_engine(
        "postgresql+asyncpg://postgres:postgres@localhost:5432/vcos_test",
        poolclass=NullPool,
        echo=False,
        future=True,
    )
    
    # Drop all tables first (in case of previous incomplete runs)
    async with engine.begin() as conn:
        await conn.execute(text("""
            DO $$ DECLARE
                r RECORD;
            BEGIN
                FOR r IN (SELECT tablename FROM pg_tables WHERE schemaname = 'public') LOOP
                    EXECUTE 'DROP TABLE IF EXISTS ' || quote_ident(r.tablename) || ' CASCADE';
                END LOOP;
            END $$;
        """))
    
    # Check tables after drop
    async with engine.begin() as conn:
        result = await conn.execute(text("SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename"))
        tables = result.fetchall()
        print(f"Tables after drop: {len(tables)}")
        for t in tables:
            print(f"  {t[0]}")
    
    # Create all tables
    from app import models  # noqa: F401
    from app.db.database import Base
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    # Check tables after create
    async with engine.begin() as conn:
        result = await conn.execute(text("SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename"))
        tables = result.fetchall()
        print(f"Tables after create: {len(tables)}")
        for t in tables:
            print(f"  {t[0]}")
    
    await engine.dispose()

# Import models first so Base is populated
from app import models  # noqa: F401
from app.db.database import Base
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool
from sqlalchemy import text

asyncio.run(test_fixture())
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from sqlalchemy.pool import NullPool
from app.db.database import Base
from app import models  # noqa: F401

async def test():
    # Create engine 1 - drop schema
    engine1 = create_async_engine(
        "postgresql+asyncpg://postgres:postgres@localhost:5432/vcos_test",
        poolclass=NullPool,
        echo=False,
        future=True,
    )
    
    async with engine1.connect() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.commit()
    
    await engine1.dispose()
    
    # Create engine 2 - create tables (completely fresh engine)
    engine2 = create_async_engine(
        "postgresql+asyncpg://postgres:postgres@localhost:5432/vcos_test",
        poolclass=NullPool,
        echo=False,
        future=True,
    )
    
    # Verify empty
    async with engine2.connect() as conn:
        tables = await conn.execute(text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'"))
        indexes = await conn.execute(text("SELECT indexname FROM pg_indexes WHERE schemaname = 'public'"))
        print(f"Tables: {tables.fetchall()}")
        print(f"Indexes: {indexes.fetchall()}")
    
    # Create all tables
    print("Creating tables with fresh engine...")
    async with engine2.connect() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.commit()
        print("Tables created!")
    
    # Verify
    async with engine2.connect() as conn:
        tables = await conn.execute(text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'"))
        indexes = await conn.execute(text("SELECT indexname FROM pg_indexes WHERE schemaname = 'public'"))
        print(f"Tables after: {len(tables.fetchall())}")
        print(f"Indexes after: {len(indexes.fetchall())}")
    
    await engine2.dispose()

asyncio.run(test())
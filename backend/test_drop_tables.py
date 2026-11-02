import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from sqlalchemy.pool import NullPool
from app.db.database import Base
from app import models  # noqa: F401

async def test():
    engine = create_async_engine(
        "postgresql+asyncpg://postgres:postgres@localhost:5432/vcos_test",
        poolclass=NullPool,
        echo=False,
        future=True,
    )
    
    # First, create tables to have something to drop
    print("Creating initial tables...")
    async with engine.connect() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.commit()
    
    # Verify
    async with engine.connect() as conn:
        tables = await conn.execute(text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'"))
        indexes = await conn.execute(text("SELECT indexname FROM pg_indexes WHERE schemaname = 'public'"))
        print(f"Initial tables: {len(tables.fetchall())}")
        print(f"Initial indexes: {len(indexes.fetchall())}")
    
    # Now drop all tables explicitly (not schema)
    print("\nDropping all tables...")
    async with engine.connect() as conn:
        # Get all table names
        tables_result = await conn.execute(text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'"))
        table_names = [row[0] for row in tables_result.fetchall()]
        
        # Drop each table with CASCADE
        for table in table_names:
            await conn.execute(text(f'DROP TABLE IF EXISTS "{table}" CASCADE'))
        await conn.commit()
    
    # Verify empty
    async with engine.connect() as conn:
        tables = await conn.execute(text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'"))
        indexes = await conn.execute(text("SELECT indexname FROM pg_indexes WHERE schemaname = 'public'"))
        print(f"Tables after drop: {tables.fetchall()}")
        print(f"Indexes after drop: {indexes.fetchall()}")
    
    # Create all tables again
    print("\nCreating tables again...")
    async with engine.connect() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.commit()
        print("Tables created!")
    
    # Verify
    async with engine.connect() as conn:
        tables = await conn.execute(text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'"))
        indexes = await conn.execute(text("SELECT indexname FROM pg_indexes WHERE schemaname = 'public'"))
        print(f"Tables after recreate: {len(tables.fetchall())}")
        print(f"Indexes after recreate: {len(indexes.fetchall())}")
    
    await engine.dispose()

asyncio.run(test())
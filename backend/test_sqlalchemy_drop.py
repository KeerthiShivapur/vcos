import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from sqlalchemy.pool import NullPool

async def test_drop():
    engine = create_async_engine(
        "postgresql+asyncpg://postgres:postgres@localhost:5432/vcos_test",
        poolclass=NullPool,
        echo=False,
        future=True,
    )
    
    # Try dropping schema
    print("Dropping schema...")
    async with engine.connect() as conn:
        result = await conn.execute(text("DROP SCHEMA public CASCADE"))
        print(f"DROP result: {result}")
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.commit()
        print("Schema recreated")
    
    # Check tables
    async with engine.connect() as conn:
        tables = await conn.execute(text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'"))
        print("Tables:", tables.fetchall())
    
    await engine.dispose()

asyncio.run(test_drop())
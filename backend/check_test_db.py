from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy import text
import asyncio
import os

async def test():
    # Use test database URL
    test_db_url = os.environ.get("TEST_DATABASE_URL", "postgresql+asyncpg://vcos:vcos@localhost:5432/vcos_test")
    
    engine = create_async_engine(
        test_db_url,
        poolclass=__import__('sqlalchemy.pool').pool.NullPool,
        connect_args={"server_settings": {"search_path": "public"}},
        echo=False,
        future=True,
    )
    
    try:
        async with AsyncSession(engine) as db:
            await db.execute(text("SET ROLE vcos"))
            await db.commit()
            
            # Check function
            result = await db.execute(text("""
                SELECT proname FROM pg_proc 
                WHERE proname = 'current_organization_id' AND pronamespace = 'public'::regnamespace
            """))
            func = result.fetchone()
            print(f'Function exists: {func}')
            
            if func:
                result = await db.execute(text("SELECT current_organization_id()"))
                val = result.scalar()
                print(f'current_organization_id(): {val}')
            else:
                print('Function does not exist in test database!')
    finally:
        await engine.dispose()

asyncio.run(test())
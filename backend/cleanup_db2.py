import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

async def cleanup_database():
    engine = create_async_engine('postgresql+asyncpg://postgres:postgres@localhost:5432/vcos_test', poolclass=None)
    
    async with engine.begin() as conn:
        # Get all tables in correct order (using information_schema)
        result = await conn.execute(text("""
            SELECT table_name FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name NOT IN ('alembic_version')
            ORDER BY table_name
        """))
        tables = [row[0] for row in result]
        
        # Disable triggers and FK checks, truncate
        await conn.execute(text("SET session_replication_role = 'replica'"))
        
        for table in tables:
            try:
                await conn.execute(text(f"TRUNCATE TABLE {table} CASCADE"))
                print(f"Truncated {table}")
            except Exception as e:
                print(f"Error truncating {table}: {e}")
        
        await conn.execute(text("SET session_replication_role = 'origin'"))
    
    await engine.dispose()
    print("Database cleanup complete")

asyncio.run(cleanup_database())
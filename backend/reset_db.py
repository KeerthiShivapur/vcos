import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

async def reset_db():
    engine = create_async_engine('postgresql+asyncpg://postgres:postgres@localhost:5432/vcos')
    async with engine.begin() as conn:
        # Drop all tables in public schema
        await conn.execute(text("""
            DO $$ DECLARE
                r RECORD;
            BEGIN
                FOR r IN (SELECT tablename FROM pg_tables WHERE schemaname = 'public') LOOP
                    EXECUTE 'DROP TABLE IF EXISTS ' || quote_ident(r.tablename) || ' CASCADE';
                END LOOP;
            END $$;
        """))
    print('All tables dropped')

asyncio.run(reset_db())
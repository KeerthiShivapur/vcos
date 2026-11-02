import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

async def check():
    engine = create_async_engine('postgresql+asyncpg://vcos:vcos@localhost:5432/vcos_test')
    async with engine.connect() as conn:
        # Check all indexes
        result = await conn.execute(text("SELECT indexname, tablename FROM pg_indexes WHERE indexname LIKE 'ix_bm_%'"))
        print('ix_bm_% indexes:', result.fetchall())
        
        # Check all tables
        result = await conn.execute(text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' ORDER BY table_name"))
        print('All tables:', result.fetchall())

asyncio.run(check())
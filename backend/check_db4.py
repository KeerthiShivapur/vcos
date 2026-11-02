import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

async def check():
    engine = create_async_engine('postgresql+asyncpg://vcos:vcos@localhost:5432/vcos_test')
    async with engine.connect() as conn:
        # Check alembic version
        result = await conn.execute(text("SELECT version_num FROM alembic_version"))
        print('Alembic version:', result.fetchall())
        
        # Check all tables
        result = await conn.execute(text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' AND table_name LIKE 'backup_%'"))
        print('Backup tables:', result.fetchall())

asyncio.run(check())
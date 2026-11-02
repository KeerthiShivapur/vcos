import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from app.db.database import Base
from app import models

async def setup():
    engine = create_async_engine('postgresql+asyncpg://vcos:vcos@localhost:5432/vcos_test', echo=False)
    async with engine.begin() as conn:
        await conn.execute(text('SET search_path TO public'))
        
        # Check if enum exists
        result = await conn.execute(text("SELECT count(*) FROM pg_type WHERE typname = 'autonomy_risk_class'"))
        print(f'Enum count: {result.scalar()}')
        
        # Check if tables exist
        result = await conn.execute(text("SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public'"))
        print(f'Tables before create_all: {result.scalar()}')
        
        # Try to create tables
        from app.db.database import Base
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()
    print('Schema created')

asyncio.run(setup())
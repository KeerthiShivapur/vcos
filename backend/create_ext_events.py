import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from app.models.canonical_integration import ExternalEvent
from app.db.database import Base

async def create_table():
    engine = create_async_engine('postgresql+asyncpg://postgres:postgres@localhost:5432/vcos_test', poolclass=None)
    
    async with engine.begin() as conn:
        # Create only the external_events table
        await conn.run_sync(Base.metadata.create_all, tables=[ExternalEvent.__table__])
    
    await engine.dispose()
    print('Table created')

asyncio.run(create_table())
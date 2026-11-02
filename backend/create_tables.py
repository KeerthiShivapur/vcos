import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from app.db.database import Base
from app import models

async def create_tables():
    engine = create_async_engine('postgresql+asyncpg://postgres:postgres@localhost:5432/vcos_gate7', echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()
    print('Tables created')

asyncio.run(create_tables())
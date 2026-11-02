import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.pool import NullPool
from sqlalchemy import text
from app.db.database import Base
from app import models

async def analyze():
    engine = create_async_engine('sqlite+aiosqlite:///test.db', poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"))
        tables = [r[0] for r in result]
        print(f'Tables: {len(tables)}')
        for t in tables[:20]:
            print(f'  {t}')
        if len(tables) > 20:
            print(f'  ... and {len(tables) - 20} more')

asyncio.run(analyze())
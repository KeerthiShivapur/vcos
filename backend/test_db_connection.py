import asyncio
import sys
sys.path.insert(0, '.')
import os
os.environ['DATABASE_URL'] = 'postgresql+asyncpg://postgres:postgres@192.168.208.1:5432/vcos4'

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

async def check():
    engine = create_async_engine('postgresql+asyncpg://postgres:postgres@192.168.208.1:5432/vcos4')
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT 1"))
        print(f'Connection test: {result.scalar()}')

asyncio.run(check())
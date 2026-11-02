import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool
from sqlalchemy import text
from app.db.database import Base
from app import models

async def test():
    engine = create_async_engine('sqlite+aiosqlite:///test.db', poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    # Check actual table names
    async with engine.connect() as conn:
        for table in ['company_attention', 'company_insights', 'documents', 'company_attentions', 'insights', 'knowledge_documents']:
            result = await conn.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name='" + table + "'"))
            exists = result.fetchone()
            print(table + ': ' + ('EXISTS' if exists else 'MISSING'))

asyncio.run(test())
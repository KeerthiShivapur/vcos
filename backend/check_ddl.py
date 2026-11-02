import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from app.db.database import Base
from app import models
from sqlalchemy.schema import CreateTable

async def check():
    engine = create_async_engine('sqlite+aiosqlite:///:memory:')
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        
        # Get the DDL for the table
        from app.models.financial_resource_procurement import ResourceRequirement
        ddl = str(CreateTable(ResourceRequirement.__table__).compile(engine))
        print(ddl)
    await engine.dispose()

asyncio.run(check())
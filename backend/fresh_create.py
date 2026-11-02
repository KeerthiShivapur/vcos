#!/usr/bin/env python
"""Fresh process to create tables"""
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from app.db.database import Base
from app import models  # noqa: F401

async def main():
    engine = create_async_engine(
        'postgresql+asyncpg://postgres:postgres@localhost:5432/vcos_gate7',
        poolclass=None,
        echo=False,
        future=True
    )
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    await engine.dispose()
    print('Tables created successfully')

if __name__ == '__main__':
    asyncio.run(main())
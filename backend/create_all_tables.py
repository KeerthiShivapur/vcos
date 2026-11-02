import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool
from app.db.database import Base
from app import models

async def main():
    # Drop and recreate database
    sync_engine = create_engine(
        'postgresql+psycopg2://postgres:postgres@localhost:5432/postgres',
        poolclass=NullPool,
        isolation_level="AUTOCOMMIT"
    )
    with sync_engine.connect() as conn:
        conn.execute(text("DROP DATABASE IF EXISTS vcos_gate7"))
        conn.execute(text("CREATE DATABASE vcos_gate7"))
    sync_engine.dispose()
    print("Database recreated")
    
    # Create tables with async engine
    async_engine = create_async_engine(
        'postgresql+asyncpg://postgres:postgres@localhost:5432/vcos_gate7',
        poolclass=NullPool,
        echo=False
    )
    
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    await async_engine.dispose()
    print("Tables created successfully")

asyncio.run(main())
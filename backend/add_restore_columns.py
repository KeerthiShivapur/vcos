import asyncio
import sys
sys.path.insert(0, '.')
import os
os.environ['DATABASE_URL'] = 'postgresql+asyncpg://postgres:postgres@192.168.208.1:5432/vcos4'

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

async def add_columns():
    engine = create_async_engine('postgresql+asyncpg://postgres:postgres@192.168.208.1:5432/vcos4')
    async with engine.connect() as conn:
        # Add missing columns to restore_operations
        await conn.execute(text("""
            ALTER TABLE restore_operations 
            ADD COLUMN IF NOT EXISTS error_phase VARCHAR(64),
            ADD COLUMN IF NOT EXISTS canonical_fingerprint VARCHAR(160),
            ADD COLUMN IF NOT EXISTS validation_passed BOOLEAN,
            ADD COLUMN IF NOT EXISTS fingerprint VARCHAR(160)
        """))
        await conn.commit()
        print("Columns added successfully")

asyncio.run(add_columns())
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

async def add_columns():
    engine = create_async_engine('postgresql+asyncpg://postgres:postgres@localhost:5432/vcos_test')
    async with engine.begin() as conn:
        # Add the new columns to organizations table
        await conn.execute(text('ALTER TABLE organizations ADD COLUMN IF NOT EXISTS employee_count INTEGER DEFAULT 0'))
        await conn.execute(text('ALTER TABLE organizations ADD COLUMN IF NOT EXISTS organizational_depth INTEGER DEFAULT 1'))
        await conn.execute(text('ALTER TABLE organizations ADD COLUMN IF NOT EXISTS organizational_unit_count INTEGER DEFAULT 0'))
        await conn.execute(text('ALTER TABLE organizations ADD COLUMN IF NOT EXISTS legal_entity_count INTEGER DEFAULT 1'))
        await conn.execute(text('ALTER TABLE organizations ADD COLUMN IF NOT EXISTS geographic_footprint_count INTEGER DEFAULT 1'))
        await conn.execute(text('ALTER TABLE organizations ADD COLUMN IF NOT EXISTS governance_complexity VARCHAR(20) DEFAULT \'simple\''))
        await conn.execute(text('ALTER TABLE organizations ADD COLUMN IF NOT EXISTS workflow_complexity VARCHAR(20) DEFAULT \'simple\''))
        await conn.execute(text('ALTER TABLE organizations ADD COLUMN IF NOT EXISTS experience_config_id VARCHAR(32)'))
        print('Columns added successfully')

asyncio.run(add_columns())
import os
os.environ['DATABASE_URL'] = 'postgresql+asyncpg://postgres:postgres@localhost:5432/vcos_test'

import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

async def fix_constraint():
    engine = create_async_engine('postgresql+asyncpg://postgres:postgres@localhost:5432/vcos_test')
    async with engine.begin() as conn:
        # Drop the existing unique constraint
        await conn.execute(text('ALTER TABLE external_identity_mappings DROP CONSTRAINT uq_eim_vcos_entity'))
        
        # Create a partial unique index that only applies when vcos_entity_id is not empty
        await conn.execute(text("""
            CREATE UNIQUE INDEX uq_eim_vcos_entity 
            ON external_identity_mappings (organization_id, connector_instance_id, vcos_entity_type, vcos_entity_id) 
            WHERE vcos_entity_id != ''
        """))
        
        print('Fixed constraint - now allows multiple pending mappings with empty vcos_entity_id')
    await engine.dispose()

asyncio.run(fix_constraint())
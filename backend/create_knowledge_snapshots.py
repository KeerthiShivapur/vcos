import asyncio
import os
os.environ['DATABASE_URL'] = 'postgresql+asyncpg://postgres:postgres@localhost:5432/vcos_test'

async def create_tables():
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy import text
    engine = create_async_engine('postgresql+asyncpg://postgres:postgres@localhost:5432/vcos_test')
    async with engine.begin() as conn:
        await conn.execute(text('''
            CREATE TABLE IF NOT EXISTS company_knowledge_snapshots (
                id VARCHAR(255) PRIMARY KEY,
                organization_id VARCHAR(255) NOT NULL,
                claim_id VARCHAR(255),
                claim_type VARCHAR(50),
                claim_version INTEGER,
                snapshot_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                valid_from TIMESTAMP WITH TIME ZONE,
                valid_to TIMESTAMP WITH TIME ZONE,
                epistemic_state VARCHAR(50),
                confidence NUMERIC(5,2),
                belief_json JSON,
                evidence_ids_json JSON,
                contradiction_ids_json JSON,
                source_event_id VARCHAR(255),
                recorded_by VARCHAR(255),
                corrected_at TIMESTAMP WITH TIME ZONE,
                corrected_by VARCHAR(255),
                correction_reason TEXT,
                supersedes_snapshot_id VARCHAR(255),
                version INTEGER DEFAULT 1,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )
        '''))
        print('company_knowledge_snapshots created')
    await engine.dispose()

asyncio.run(create_tables())
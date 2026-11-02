import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool
from sqlalchemy import text
from app.db.database import Base
from app import models

async def analyze():
    engine = create_async_engine('sqlite+aiosqlite:///test.db', poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    # Check indexes on key tables
    key_tables = [
        'employees', 'projects', 'tasks', 'meetings', 'decisions',
        'documents', 'conversations', 'messages', 'canonical_observations',
        'security_events', 'canonical_operations', 'company_attentions',
        'company_state_snapshots', 'organizational_learning',
        'patterns', 'insights', 'knowledge_documents',
    ]
    
    async with engine.connect() as conn:
        for table in key_tables:
            result = await conn.execute(text(f"PRAGMA index_list({table})"))
            indexes = result.fetchall()
            if indexes:
                print(f"\n{table}: {len(indexes)} indexes")
                for idx in indexes:
                    print(f"  {idx[1]} (unique={idx[2]})")
            else:
                print(f"\n{table}: NO INDEXES")

asyncio.run(analyze())
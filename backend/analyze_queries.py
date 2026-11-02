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
    
    # Check query plans for key operations
    async with engine.connect() as conn:
        # 1. Company Brain query pattern
        print("=== Company Brain Query ===")
        result = await conn.execute(text("""
            EXPLAIN QUERY PLAN
            SELECT id, organization_id, name, description, status, progress
            FROM projects
            WHERE organization_id = 'test-org' AND status IN ('active', 'planning')
            ORDER BY updated_at DESC LIMIT 20
        """))
        for row in result:
            print(f"  {row[0]}|{row[1]}|{row[2]}|{row[3]}")
        
        print("\n=== Task Query (by project) ===")
        result = await conn.execute(text("""
            EXPLAIN QUERY PLAN
            SELECT id, title, status, priority, assignee_id
            FROM tasks
            WHERE organization_id = 'test-org' AND project_id = 'proj-1'
            ORDER BY updated_at DESC LIMIT 50
        """))
        for row in result:
            print(f"  {row[0]}|{row[1]}|{row[2]}|{row[3]}")
        
        print("\n=== Meeting Query ===")
        result = await conn.execute(text("""
            EXPLAIN QUERY PLAN
            SELECT id, title, meeting_type, status, start_at
            FROM meetings
            WHERE organization_id = 'test-org' AND start_at > datetime('now', '-30 days')
            ORDER BY start_at DESC LIMIT 20
        """))
        for row in result:
            print(f"  {row[0]}|{row[1]}|{row[2]}|{row[3]}")
        
        print("\n=== Decision Query ===")
        result = await conn.execute(text("""
            EXPLAIN QUERY PLAN
            SELECT id, title, status, decision_date
            FROM decisions
            WHERE organization_id = 'test-org' AND project_id = 'proj-1'
            ORDER BY decision_date DESC LIMIT 20
        """))
        for row in result:
            print(f"  {row[0]}|{row[1]}|{row[2]}|{row[3]}")
        
        print("\n=== Document Search (LIKE) ===")
        result = await conn.execute(text("""
            EXPLAIN QUERY PLAN
            SELECT id, title, category, status
            FROM documents
            WHERE organization_id = 'test-org' AND title LIKE '%api%'
            ORDER BY updated_at DESC LIMIT 20
        """))
        for row in result:
            print(f"  {row[0]}|{row[1]}|{row[2]}|{row[3]}")
        
        print("\n=== Conversation + Messages (N+1 check) ===")
        result = await conn.execute(text("""
            EXPLAIN QUERY PLAN
            SELECT c.id, c.title, c.type, c.message_count
            FROM conversations c
            WHERE c.organization_id = 'test-org' AND c.id IN (
                SELECT conversation_id FROM conversation_members 
                WHERE organization_id = 'test-org' AND employee_id = 'emp-1'
            )
            ORDER BY c.updated_at DESC LIMIT 20
        """))
        for row in result:
            print(f"  {row[0]}|{row[1]}|{row[2]}|{row[3]}")
        
        print("\n=== Canonical Observation Query ===")
        result = await conn.execute(text("""
            EXPLAIN QUERY PLAN
            SELECT id, observation_type, severity, observed_at
            FROM canonical_observations
            WHERE organization_id = 'test-org' AND observed_at > datetime('now', '-7 days')
            ORDER BY observed_at DESC LIMIT 100
        """))
        for row in result:
            print(f"  {row[0]}|{row[1]}|{row[2]}|{row[3]}")
        
        print("\n=== Security Events Query ===")
        result = await conn.execute(text("""
            EXPLAIN QUERY PLAN
            SELECT id, event_type, severity, status, created_at
            FROM security_events
            WHERE organization_id = 'test-org' AND created_at > datetime('now', '-30 days')
            ORDER BY created_at DESC LIMIT 50
        """))
        for row in result:
            print(f"  {row[0]}|{row[1]}|{row[2]}|{row[3]}")

asyncio.run(analyze())
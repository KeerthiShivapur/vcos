"""Test to verify connection reuse with context leak test."""

import asyncio
import sys
from pathlib import Path

# Add backend to path
BACKEND_DIR = Path(__file__).parent
sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import text
from app.db.database import engine, get_db


async def test_context_leak_with_connection_ids():
    """Test that tenant context doesn't leak using the app's engine."""
    
    org_a_id = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    org_b_id = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
    
    print("=== Test: Connection Reuse Context Leak (with connection IDs) ===")
    
    # Request 1: Tenant A using get_db()
    print("\n1. Request for Tenant A via get_db()")
    async for session in get_db():
        conn = await session.connection()
        raw_conn = await conn.get_raw_connection()
        print(f"   [DEBUG] Session: {id(session)}, Connection: {id(conn)}, Raw: {id(raw_conn)}")
        await session.execute(text("SET ROLE vcos"))
        await session.execute(text("SELECT set_config('app.current_organization_id', :org_id, false)"), {"org_id": org_a_id})
        result = await session.execute(text("SELECT current_organization_id()"))
        val = result.scalar()
        print(f"   After setting context: {val}")
        # Session will be committed and closed by get_db()
    
    print("   [DEBUG] After get_db() iteration 1")
    
    # Request 2: Tenant B (should NOT see Tenant A's context)
    print("\n2. Request for Tenant B via get_db() (new session from pool)")
    async for session in get_db():
        conn = await session.connection()
        raw_conn = await conn.get_raw_connection()
        print(f"   [DEBUG] Session: {id(session)}, Connection: {id(conn)}, Raw: {id(raw_conn)}")
        await session.execute(text("SET ROLE vcos"))
        # Don't set context - should be empty if no leak
        result = await session.execute(text("SELECT current_organization_id()"))
        val = result.scalar()
        print(f"   Before setting context: {val}")
        
        if val == org_a_id:
            print("   [LEAK] Tenant A's context leaked to Tenant B's session!")
        elif val is None or val == '':
            print("   [OK] No leak: Context properly reset")
        else:
            print(f"   ? Unexpected value: {val}")
        
        # Now set Tenant B's context
        await session.execute(text("SELECT set_config('app.current_organization_id', :org_id, false)"), {"org_id": org_b_id})
        result = await session.execute(text("SELECT current_organization_id()"))
        val = result.scalar()
        print(f"   After setting Tenant B context: {val}")
        # Session will be committed and closed by get_db()
    
    print("   [DEBUG] After get_db() iteration 2")
    
    # Request 3: Tenant A again (should NOT see Tenant B's context)
    print("\n3. Request for Tenant A again via get_db()")
    async for session in get_db():
        conn = await session.connection()
        raw_conn = await conn.get_raw_connection()
        print(f"   [DEBUG] Session: {id(session)}, Connection: {id(conn)}, Raw: {id(raw_conn)}")
        await session.execute(text("SET ROLE vcos"))
        # Don't set context - should be empty if no leak
        result = await session.execute(text("SELECT current_organization_id()"))
        val = result.scalar()
        print(f"   Before setting context: {val}")
        
        if val == org_b_id:
            print("   [LEAK] Tenant B's context leaked to Tenant A's session!")
        elif val is None or val == '':
            print("   [OK] No leak: Context properly reset")
        else:
            print(f"   ? Unexpected value: {val}")
        
        # Session will be committed and closed by get_db()
    
    print("   [DEBUG] After get_db() iteration 3")
    print("\n=== Test Complete ===")


if __name__ == "__main__":
    asyncio.run(test_context_leak_with_connection_ids())
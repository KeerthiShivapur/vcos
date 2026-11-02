"""Test to verify connection identity."""

import asyncio
import sys
from pathlib import Path

# Add backend to path
BACKEND_DIR = Path(__file__).parent
sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import text
from app.db.database import engine, get_db


async def test_connection_identity():
    """Test if connections are truly distinct."""
    
    print("=== Test: Connection Identity ===")
    
    raw_connections = []
    
    for i in range(5):
        print(f"\n{i+1}. Request")
        async for session in get_db():
            conn = await session.connection()
            raw_conn = await conn.get_raw_connection()
            # Get the underlying asyncpg connection
            asyncpg_conn = raw_conn._connection if hasattr(raw_conn, '_connection') else raw_conn
            print(f"   Raw: {id(raw_conn)}, asyncpg: {id(asyncpg_conn)}")
            # Check if it's the same object
            for j, existing in enumerate(raw_connections):
                if raw_conn is existing:
                    print(f"   SAME as request {j+1}!")
                    break
            else:
                raw_connections.append(raw_conn)
                print(f"   NEW connection (total unique: {len(raw_connections)})")
    
    print(f"\nTotal unique raw connections: {len(raw_connections)}")
    print("\n=== Test Complete ===")


if __name__ == "__main__":
    import asyncio
    import sys
    from pathlib import Path
    BACKEND_DIR = Path(__file__).parent
    sys.path.insert(0, str(BACKEND_DIR))
    from app.db.database import get_db
    asyncio.run(test_connection_identity())
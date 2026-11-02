"""Test to verify connection reuse."""

import asyncio
import sys
from pathlib import Path

# Add backend to path
BACKEND_DIR = Path(__file__).parent
sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import text
from app.db.database import engine, get_db


async def test_connection_reuse():
    """Test if connections are being reused."""
    
    print("=== Test: Connection Reuse ===")
    
    for i in range(5):
        print(f"\n{i+1}. Request")
        async for session in get_db():
            # Get the underlying connection
            conn = await session.connection()
            # Get the raw DBAPI connection
            raw_conn = await conn.get_raw_connection()
            print(f"   Session: {id(session)}, Connection: {id(conn)}, Raw: {id(raw_conn) if raw_conn else 'N/A'}")
    
    print("\n=== Test Complete ===")


if __name__ == "__main__":
    asyncio.run(test_connection_reuse())
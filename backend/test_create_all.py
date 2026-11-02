import asyncio
from app.db.database import engine, Base
from sqlalchemy import inspect

async def main():
    async with engine.begin() as conn:
        # Drop all tables first
        await conn.run_sync(Base.metadata.drop_all)
        print("All tables dropped")
        
        # Create all tables with verbose output
        await conn.run_sync(Base.metadata.create_all)
        print("All tables created")
        
        # Check what tables exist
        def get_tables(sync_conn):
            return inspect(sync_conn).get_table_names()
        tables = await conn.run_sync(get_tables)
        print("\nTables in database:")
        for t in sorted(tables):
            print(f"  {t}")

asyncio.run(main())
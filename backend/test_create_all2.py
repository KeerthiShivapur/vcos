import asyncio
from app.db.database import engine, Base
from sqlalchemy import inspect

async def main():
    async with engine.begin() as conn:
        # Drop all tables first
        await conn.run_sync(Base.metadata.drop_all)
        print("All tables dropped")
        
        # Check metadata before create_all
        print(f"Tables in metadata before create_all: {len(Base.metadata.tables)}")
        if "employees" in Base.metadata.tables:
            print("employees IN metadata")
        else:
            print("employees MISSING from metadata!")
        
        # Create all tables with verbose output
        await conn.run_sync(Base.metadata.create_all)
        print("All tables created")
        
        # Check metadata after create_all
        print(f"Tables in metadata after create_all: {len(Base.metadata.tables)}")
        
        # Check what tables exist
        def get_tables(sync_conn):
            return inspect(sync_conn).get_table_names()
        tables = await conn.run_sync(get_tables)
        print("\nTables in database:")
        for t in sorted(tables):
            print(f"  {t}")

asyncio.run(main())
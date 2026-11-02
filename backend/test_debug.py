import asyncio
from app.db.database import engine, Base
from sqlalchemy import inspect

async def main():
    async with engine.begin() as conn:
        # Check what tables are in metadata BEFORE create_all
        print("Tables in Base.metadata BEFORE create_all:")
        for t in Base.metadata.tables:
            print(f"  {t}")
        
        # Check if user_roles and roles are in metadata
        if "user_roles" in Base.metadata.tables:
            print("\nuser_roles EXISTS in metadata")
        else:
            print("\nuser_roles MISSING from metadata!")
            
        if "roles" in Base.metadata.tables:
            print("roles EXISTS in metadata")
        else:
            print("roles MISSING from metadata!")
        
        # Drop all tables first
        await conn.run_sync(Base.metadata.drop_all)
        print("\nAll tables dropped")
        
        # Create all tables
        await conn.run_sync(Base.metadata.create_all)
        print("All tables created")
        
        # Check what tables exist
        def get_tables(sync_conn):
            return inspect(sync_conn).get_table_names()
        tables = await conn.run_sync(get_tables)
        print("\nTables in database AFTER create_all:")
        for t in sorted(tables):
            print(f"  {t}")
        
        # Check if user_roles exists
        if "user_roles" in tables:
            print("\nuser_roles table EXISTS")
        else:
            print("\nuser_roles table MISSING!")
            
        if "roles" in tables:
            print("roles table EXISTS")
        else:
            print("roles table MISSING!")

asyncio.run(main())
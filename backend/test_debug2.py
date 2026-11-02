import asyncio
from app.db.database import engine, Base
from sqlalchemy import inspect

async def main():
    print("Starting test_debug...")
    
    # Test importing role module inside async function
    print("\nImporting role module inside async function...")
    try:
        from app.models import role
        print("role module imported successfully")
    except Exception as e:
        print(f"ERROR importing role: {e}")
        import traceback
        traceback.print_exc()
    
    # Check Base.metadata
    from app.models.base import Base
    print(f"\nTables in Base.metadata: {len(Base.metadata.tables)}")
    if "user_roles" in Base.metadata.tables:
        print("user_roles IN metadata")
    else:
        print("user_roles MISSING from metadata!")
    
    if "roles" in Base.metadata.tables:
        print("roles IN metadata")
    else:
        print("roles MISSING from metadata!")
    
    async with engine.begin() as conn:
        # Drop all tables first
        await conn.run_sync(Base.metadata.drop_all)
        print("All tables dropped")
        
        # Create all tables
        await conn.run_sync(Base.metadata.create_all)
        print("All tables created")
        
        # Check what tables exist
        def get_tables(sync_conn):
            return inspect(sync_conn).get_table_names()
        tables = await conn.run_sync(get_tables)
        print("\nTables in database:")
        for t in sorted(tables):
            print(f"  {t}")
        
        if "user_roles" in tables:
            print("\nuser_roles table EXISTS")
        else:
            print("\nuser_roles table MISSING!")
            
        if "roles" in tables:
            print("roles table EXISTS")
        else:
            print("roles table MISSING!")

asyncio.run(main())
#!/usr/bin/env python
"""
Fix PostgreSQL schema permissions for the vcos role.
"""
import asyncio
import asyncpg


async def fix_permissions():
    print("=" * 60)
    print("FIXING: PostgreSQL schema permissions")
    print("=" * 60)
    
    # Connect as superuser or role that can grant permissions
    # For local dev, we might need to connect as postgres user
    # But let's try with vcos first
    conn = await asyncpg.connect('postgresql://vcos:vcos@localhost:5432/vcos_test')
    try:
        # Grant USAGE on public schema
        print("\nGranting USAGE on public schema to vcos...")
        await conn.execute('GRANT USAGE ON SCHEMA public TO vcos')
        print("  SUCCESS")
        
        # Grant CREATE on public schema (should already have this)
        print("\nGranting CREATE on public schema to vcos...")
        await conn.execute('GRANT CREATE ON SCHEMA public TO vcos')
        print("  SUCCESS")
        
        # Verify
        result = await conn.fetchval("SELECT has_schema_privilege('vcos', 'public', 'USAGE')")
        print(f"\nUSAGE privilege: {result}")
        result = await conn.fetchval("SELECT has_schema_privilege('vcos', 'public', 'CREATE')")
        print(f"CREATE privilege: {result}")
        
        # Test if current_schema() now works
        result = await conn.fetchval('SELECT current_schema()')
        print(f"\ncurrent_schema() after grant: {result}")
        
    except Exception as e:
        print(f"Error: {e}")
    finally:
        await conn.close()
    
    # Now test with a fresh connection
    print("\n" + "=" * 60)
    print("TESTING: Fresh connection after grants")
    print("=" * 60)
    
    conn = await asyncpg.connect('postgresql://vcos:vcos@localhost:5432/vcos_test')
    try:
        result = await conn.fetchval('SHOW search_path')
        print(f"search_path: {result}")
        result = await conn.fetchval('SELECT current_schema()')
        print(f"current_schema(): {result}")
        result = await conn.fetchval('SELECT current_schemas(true)')
        print(f"current_schemas(true): {result}")
        
        print("\nAttempting unqualified CREATE TABLE...")
        try:
            await conn.execute('CREATE TABLE diag_test_after_grant (id INT)')
            print("SUCCESS: CREATE TABLE worked")
            await conn.execute('DROP TABLE diag_test_after_grant')
        except Exception as e:
            print(f"FAILED: {e}")
            
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(fix_permissions())
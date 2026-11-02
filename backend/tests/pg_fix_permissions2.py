#!/usr/bin/env python
"""
Fix PostgreSQL schema permissions - try as superuser.
"""
import asyncio
import asyncpg


async def fix_permissions_superuser():
    print("=" * 60)
    print("FIXING: PostgreSQL schema permissions as superuser")
    print("=" * 60)
    
    # Try connecting as postgres user (superuser)
    try:
        conn = await asyncpg.connect('postgresql://postgres@localhost:5432/vcos_test')
        print("Connected as postgres superuser")
    except Exception as e:
        print(f"Cannot connect as postgres: {e}")
        # Try with vcos but ensure we commit
        conn = await asyncpg.connect('postgresql://vcos:vcos@localhost:5432/vcos_test')
    
    try:
        # Grant USAGE on public schema
        print("\nGranting USAGE on public schema to vcos...")
        await conn.execute('GRANT USAGE ON SCHEMA public TO vcos')
        print("  SUCCESS")
        
        # Grant CREATE on public schema
        print("\nGranting CREATE on public schema to vcos...")
        await conn.execute('GRANT CREATE ON SCHEMA public TO vcos')
        print("  SUCCESS")
        
        # Also ensure vcos can create tables
        print("\nGranting ALL on public schema to vcos...")
        await conn.execute('GRANT ALL ON SCHEMA public TO vcos')
        print("  SUCCESS")
        
        # Verify from superuser perspective
        result = await conn.fetchval("SELECT has_schema_privilege('vcos', 'public', 'USAGE')")
        print(f"\nUSAGE privilege (from superuser): {result}")
        result = await conn.fetchval("SELECT has_schema_privilege('vcos', 'public', 'CREATE')")
        print(f"CREATE privilege (from superuser): {result}")
        
        # Check if we need to grant on ALL tables in public
        print("\nGranting ALL on ALL TABLES IN SCHEMA public TO vcos...")
        await conn.execute('GRANT ALL ON ALL TABLES IN SCHEMA public TO vcos')
        print("  SUCCESS")
        
        print("\nGranting ALL ON ALL SEQUENCES IN SCHEMA public TO vcos...")
        await conn.execute('GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO vcos')
        print("  SUCCESS")
        
        # Set default privileges
        print("\nSetting default privileges for future tables...")
        await conn.execute('ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO vcos')
        print("  SUCCESS")
        await conn.execute('ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO vcos')
        print("  SUCCESS")
        
    except Exception as e:
        print(f"Error: {e}")
    finally:
        await conn.close()
    
    # Now test with a fresh vcos connection
    print("\n" + "=" * 60)
    print("TESTING: Fresh vcos connection after superuser grants")
    print("=" * 60)
    
    conn = await asyncpg.connect('postgresql://vcos:vcos@localhost:5432/vcos_test')
    try:
        result = await conn.fetchval('SHOW search_path')
        print(f"search_path: {result}")
        result = await conn.fetchval('SELECT current_schema()')
        print(f"current_schema(): {result}")
        result = await conn.fetchval('SELECT current_schemas(true)')
        print(f"current_schemas(true): {result}")
        result = await conn.fetchval("SELECT has_schema_privilege(current_user, 'public', 'USAGE')")
        print(f"USAGE privilege: {result}")
        
        print("\nAttempting unqualified CREATE TABLE...")
        try:
            await conn.execute('CREATE TABLE diag_test_superuser_grant (id INT)')
            print("SUCCESS: CREATE TABLE worked")
            await conn.execute('DROP TABLE diag_test_superuser_grant')
        except Exception as e:
            print(f"FAILED: {e}")
            
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(fix_permissions_superuser())
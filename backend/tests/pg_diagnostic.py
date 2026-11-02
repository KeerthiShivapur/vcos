#!/usr/bin/env python
"""
Minimal PostgreSQL DDL schema diagnostic.
Reproduces the "no schema has been selected to create in" failure.
"""
import asyncio
import asyncpg
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool


async def diagnose_asyncpg():
    print("=" * 60)
    print("DIAGNOSTIC: asyncpg connection")
    print("=" * 60)
    
    # Test 1: Default connection
    print("\n1. Default asyncpg connection:")
    conn = await asyncpg.connect('postgresql://vcos:vcos@localhost:5432/vcos_test')
    try:
        result = await conn.fetchval('SHOW search_path')
        print(f"   search_path: {result}")
        result = await conn.fetchval('SELECT current_schema()')
        print(f"   current_schema(): {result}")
        result = await conn.fetchval('SELECT current_schemas(true)')
        print(f"   current_schemas(true): {result}")
        result = await conn.fetchval('SELECT current_database()')
        print(f"   current_database(): {result}")
        result = await conn.fetchval('SELECT current_user')
        print(f"   current_user: {result}")
        result = await conn.fetchval("SELECT count(*) FROM information_schema.schemata WHERE schema_name = 'public'")
        print(f"   public schema exists: {result}")
        result = await conn.fetchval("SELECT has_schema_privilege(current_user, 'public', 'USAGE')")
        print(f"   has USAGE on public: {result}")
        result = await conn.fetchval("SELECT has_schema_privilege(current_user, 'public', 'CREATE')")
        print(f"   has CREATE on public: {result}")
        
        # Try unqualified DDL
        print("\n   Attempting unqualified CREATE TABLE...")
        try:
            await conn.execute('CREATE TABLE diag_test_default (id INT)')
            print("   SUCCESS: CREATE TABLE worked")
            await conn.execute('DROP TABLE diag_test_default')
        except Exception as e:
            print(f"   FAILED: {e}")
        
        # Try qualified DDL
        print("\n   Attempting qualified CREATE TABLE...")
        try:
            await conn.execute('CREATE TABLE public.diag_test_qualified (id INT)')
            print("   SUCCESS: CREATE TABLE public. worked")
            await conn.execute('DROP TABLE public.diag_test_qualified')
        except Exception as e:
            print(f"   FAILED: {e}")
    finally:
        await conn.close()
    
    # Test 2: Connection with server_settings
    print("\n2. asyncpg connection with server_settings={'search_path': 'public'}:")
    conn = await asyncpg.connect('postgresql://vcos:vcos@localhost:5432/vcos_test', server_settings={'search_path': 'public'})
    try:
        result = await conn.fetchval('SHOW search_path')
        print(f"   search_path: {result}")
        result = await conn.fetchval('SELECT current_schema()')
        print(f"   current_schema(): {result}")
        
        print("\n   Attempting unqualified CREATE TABLE...")
        try:
            await conn.execute('CREATE TABLE diag_test_settings (id INT)')
            print("   SUCCESS: CREATE TABLE worked")
            await conn.execute('DROP TABLE diag_test_settings')
        except Exception as e:
            print(f"   FAILED: {e}")
    finally:
        await conn.close()
    
    # Test 3: SET search_path then DDL
    print("\n3. asyncpg connection with explicit SET search_path:")
    conn = await asyncpg.connect('postgresql://vcos:vcos@localhost:5432/vcos_test')
    try:
        await conn.execute('SET search_path TO public')
        result = await conn.fetchval('SHOW search_path')
        print(f"   search_path: {result}")
        result = await conn.fetchval('SELECT current_schema()')
        print(f"   current_schema(): {result}")
        
        print("\n   Attempting unqualified CREATE TABLE...")
        try:
            await conn.execute('CREATE TABLE diag_test_set (id INT)')
            print("   SUCCESS: CREATE TABLE worked")
            await conn.execute('DROP TABLE diag_test_set')
        except Exception as e:
            print(f"   FAILED: {e}")
    finally:
        await conn.close()


def diagnose_psycopg2():
    print("\n" + "=" * 60)
    print("DIAGNOSTIC: psycopg2 (sync) connection")
    print("=" * 60)
    
    engine = create_engine('postgresql+psycopg2://vcos:vcos@localhost:5432/vcos_test', echo=False)
    with engine.connect() as conn:
        result = conn.execute(text('SHOW search_path')).scalar()
        print(f"search_path: {result}")
        result = conn.execute(text('SELECT current_schema()')).scalar()
        print(f"current_schema(): {result}")
        result = conn.execute(text('SELECT current_schemas(true)')).scalar()
        print(f"current_schemas(true): {result}")
        result = conn.execute(text('SELECT current_database()')).scalar()
        print(f"current_database(): {result}")
        result = conn.execute(text('SELECT current_user')).scalar()
        print(f"current_user: {result}")
        result = conn.execute(text("SELECT count(*) FROM information_schema.schemata WHERE schema_name = 'public'")).scalar()
        print(f"public schema exists: {result}")
        result = conn.execute(text("SELECT has_schema_privilege(current_user, 'public', 'USAGE')")).scalar()
        print(f"has USAGE on public: {result}")
        result = conn.execute(text("SELECT has_schema_privilege(current_user, 'public', 'CREATE')")).scalar()
        print(f"has CREATE on public: {result}")
        
        print("\nAttempting unqualified CREATE TABLE...")
        try:
            conn.execute(text('CREATE TABLE diag_test_psycopg2 (id INT)'))
            conn.commit()
            print("SUCCESS: CREATE TABLE worked")
            conn.execute(text('DROP TABLE diag_test_psycopg2'))
            conn.commit()
        except Exception as e:
            print(f"FAILED: {e}")
            
            print("\nAttempting qualified CREATE TABLE...")
            try:
                conn.execute(text('CREATE TABLE public.diag_test_psycopg2_q (id INT)'))
                conn.commit()
                print("SUCCESS: CREATE TABLE public. worked")
                conn.execute(text('DROP TABLE public.diag_test_psycopg2_q'))
                conn.commit()
            except Exception as e2:
                print(f"FAILED: {e2}")
    engine.dispose()


async def diagnose_sqlalchemy_async():
    print("\n" + "=" * 60)
    print("DIAGNOSTIC: SQLAlchemy async engine")
    print("=" * 60)
    
    # Test 1: Default async engine
    print("\n1. Default async engine:")
    engine = create_async_engine('postgresql+asyncpg://vcos:vcos@localhost:5432/vcos_test', echo=False)
    async with engine.begin() as conn:
        result = await conn.execute(text('SHOW search_path'))
        print(f"search_path: {result.scalar()}")
        result = await conn.execute(text('SELECT current_schema()'))
        print(f"current_schema(): {result.scalar()}")
        result = await conn.execute(text('SELECT current_schemas(true)'))
        print(f"current_schemas(true): {result.scalar()}")
        
        print("\nAttempting unqualified CREATE TABLE...")
        try:
            await conn.execute(text('CREATE TABLE diag_test_sa_async (id INT)'))
            print("SUCCESS: CREATE TABLE worked")
            await conn.execute(text('DROP TABLE diag_test_sa_async'))
        except Exception as e:
            print(f"FAILED: {e}")
    await engine.dispose()
    
    # Test 2: Async engine with connect_args
    print("\n2. Async engine with connect_args={'server_settings': {'search_path': 'public'}}:")
    engine = create_async_engine(
        'postgresql+asyncpg://vcos:vcos@localhost:5432/vcos_test',
        echo=False,
        connect_args={'server_settings': {'search_path': 'public'}}
    )
    async with engine.begin() as conn:
        result = await conn.execute(text('SHOW search_path'))
        print(f"search_path: {result.scalar()}")
        result = await conn.execute(text('SELECT current_schema()'))
        print(f"current_schema(): {result.scalar()}")
        
        print("\nAttempting unqualified CREATE TABLE...")
        try:
            await conn.execute(text('CREATE TABLE diag_test_sa_async2 (id INT)'))
            print("SUCCESS: CREATE TABLE worked")
            await conn.execute(text('DROP TABLE diag_test_sa_async2'))
        except Exception as e:
            print(f"FAILED: {e}")
    await engine.dispose()
    
    # Test 3: Async engine with event listener
    print("\n3. Async engine with connect event listener:")
    from sqlalchemy import event
    engine = create_async_engine('postgresql+asyncpg://vcos:vcos@localhost:5432/vcos_test', echo=False)
    
    @event.listens_for(engine.sync_engine, "connect")
    def set_search_path(dbapi_connection, connection_record):
        if hasattr(dbapi_connection, "execute"):
            dbapi_connection.execute("SET search_path TO public")
    
    async with engine.begin() as conn:
        result = await conn.execute(text('SHOW search_path'))
        print(f"search_path: {result.scalar()}")
        result = await conn.execute(text('SELECT current_schema()'))
        print(f"current_schema(): {result.scalar()}")
        
        print("\nAttempting unqualified CREATE TABLE...")
        try:
            await conn.execute(text('CREATE TABLE diag_test_sa_async3 (id INT)'))
            print("SUCCESS: CREATE TABLE worked")
            await conn.execute(text('DROP TABLE diag_test_sa_async3'))
        except Exception as e:
            print(f"FAILED: {e}")
    await engine.dispose()


async def main():
    await diagnose_asyncpg()
    diagnose_psycopg2()
    await diagnose_sqlalchemy_async()


if __name__ == "__main__":
    asyncio.run(main())
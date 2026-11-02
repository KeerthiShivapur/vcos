import asyncpg
import asyncio

async def check_drop():
    conn = await asyncpg.connect('postgresql://postgres:postgres@localhost:5432/vcos_test')
    
    # First create some tables
    print("Creating test tables...")
    await conn.execute("CREATE TABLE test1 (id INT)")
    await conn.execute("CREATE INDEX ix_test1 ON test1(id)")
    
    tables = await conn.fetch("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
    print("Tables before drop:", [t['tablename'] for t in tables])
    
    indexes = await conn.fetch("SELECT indexname FROM pg_indexes WHERE schemaname = 'public'")
    print("Indexes before drop:", [i['indexname'] for i in indexes])
    
    # Try dropping schema
    print("\nDropping schema...")
    await conn.execute("DROP SCHEMA public CASCADE")
    print("Creating schema...")
    await conn.execute("CREATE SCHEMA public")
    
    # Check again
    tables = await conn.fetch("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
    print("Tables after drop/create:", [t['tablename'] for t in tables])
    
    indexes = await conn.fetch("SELECT indexname FROM pg_indexes WHERE schemaname = 'public'")
    print("Indexes after drop/create:", [i['indexname'] for i in indexes])
    
    await conn.close()

asyncio.run(check_drop())
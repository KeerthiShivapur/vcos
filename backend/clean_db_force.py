import asyncpg
import asyncio

async def clean_db():
    # Connect to the default postgres database to drop/create
    conn = await asyncpg.connect('postgresql://postgres:postgres@localhost:5432/postgres')
    
    # Terminate all connections to vcos_gate7
    await conn.execute("""
        SELECT pg_terminate_backend(pid)
        FROM pg_stat_activity
        WHERE datname = 'vcos_gate7' AND pid <> pg_backend_pid()
    """)
    
    # Drop and recreate database
    await conn.execute('DROP DATABASE IF EXISTS vcos_gate7 WITH (FORCE)')
    await conn.execute('CREATE DATABASE vcos_gate7')
    print('Database dropped and recreated')
    await conn.close()
    
    await asyncio.sleep(1)
    
    # Now connect to the new database and verify it's empty
    conn = await asyncpg.connect('postgresql://postgres:postgres@localhost:5432/vcos_gate7')
    tables = await conn.fetch("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
    print('Tables in new vcos_gate7:', [t['tablename'] for t in tables])
    
    # Drop schema public and recreate
    await conn.execute('DROP SCHEMA public CASCADE')
    await conn.execute('CREATE SCHEMA public')
    await conn.execute('GRANT ALL ON SCHEMA public TO postgres')
    await conn.execute('GRANT ALL ON SCHEMA public TO public')
    print('Schema public recreated')
    
    tables = await conn.fetch("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
    print('Tables after schema recreate:', [t['tablename'] for t in tables])
    
    await conn.close()

asyncio.run(clean_db())
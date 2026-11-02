import asyncio
import asyncpg

async def verify():
    conn = await asyncpg.connect('postgresql://postgres:postgres@localhost:5432/vcos_test')
    # Check all required tables exist
    tables = await conn.fetch('''
        SELECT table_name FROM information_schema.tables 
        WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
    ''')
    print(f'Tables found: {len(tables)}')
    for t in tables:
        print(f'  - {t["table_name"]}')
    # Check key constraints
    fks = await conn.fetch('''
        SELECT count(*) FROM information_schema.table_constraints 
        WHERE constraint_type = 'FOREIGN KEY'
    ''')
    print(f'Foreign keys: {fks[0]["count"]}')
    uks = await conn.fetch('''
        SELECT count(*) FROM information_schema.table_constraints 
        WHERE constraint_type = 'UNIQUE'
    ''')
    print(f'Unique constraints: {uks[0]["count"]}')
    indexes = await conn.fetch('''
        SELECT count(*) FROM pg_indexes WHERE schemaname = 'public'
    ''')
    print(f'Indexes: {indexes[0]["count"]}')
    await conn.close()

asyncio.run(verify())
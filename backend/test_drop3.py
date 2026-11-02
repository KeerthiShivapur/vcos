import asyncpg
import asyncio

async def test_drop():
    conn = await asyncpg.connect('postgresql://postgres:postgres@localhost:5432/vcos_test')
    
    # Create some tables first
    await conn.execute('CREATE TABLE test_table (id INT PRIMARY KEY)')
    await conn.execute('CREATE INDEX test_idx ON test_table (id)')
    
    # Check tables before
    tables = await conn.fetch('''
        SELECT tablename FROM pg_tables 
        WHERE schemaname = 'public'
        ORDER BY tablename
    ''')
    print(f'Tables before: {len(tables)}')
    for t in tables:
        print(f'  {t["tablename"]}')
    
    # Check indexes
    indexes = await conn.fetch('''
        SELECT indexname FROM pg_indexes 
        WHERE schemaname = 'public'
        ORDER BY indexname
    ''')
    print(f'Indexes before: {len(indexes)}')
    for i in indexes:
        print(f'  {i["indexname"]}')
    
    # Try the DO block
    result = await conn.execute('''
        DO $$ DECLARE
            r RECORD;
        BEGIN
            FOR r IN (SELECT tablename FROM pg_tables WHERE schemaname = 'public') LOOP
                EXECUTE 'DROP TABLE IF EXISTS ' || quote_ident(r.tablename) || ' CASCADE';
            END LOOP;
        END $$;
    ''')
    print(f'DO block result: {result}')
    
    # Check tables after
    tables = await conn.fetch('''
        SELECT tablename FROM pg_tables 
        WHERE schemaname = 'public'
        ORDER BY tablename
    ''')
    print(f'Tables after: {len(tables)}')
    for t in tables:
        print(f'  {t["tablename"]}')
    
    # Check indexes
    indexes = await conn.fetch('''
        SELECT indexname FROM pg_indexes 
        WHERE schemaname = 'public'
        ORDER BY indexname
    ''')
    print(f'Indexes after: {len(indexes)}')
    for i in indexes:
        print(f'  {i["indexname"]}')
    
    await conn.close()

asyncio.run(test_drop())
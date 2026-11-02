import asyncpg
import asyncio

async def test_drop():
    conn = await asyncpg.connect('postgresql://postgres:postgres@localhost:5432/vcos_test')
    
    # Check tables before
    tables = await conn.fetch('''
        SELECT tablename FROM pg_tables 
        WHERE schemaname = 'public'
        ORDER BY tablename
    ''')
    print(f'Tables before: {len(tables)}')
    
    # Try the DO block
    await conn.execute('''
        DO $$ DECLARE
            r RECORD;
        BEGIN
            FOR r IN (SELECT tablename FROM pg_tables WHERE schemaname = 'public') LOOP
                EXECUTE 'DROP TABLE IF EXISTS ' || quote_ident(r.tablename) || ' CASCADE';
            END LOOP;
        END $$;
    ''')
    
    # Check tables after
    tables = await conn.fetch('''
        SELECT tablename FROM pg_tables 
        WHERE schemaname = 'public'
        ORDER BY tablename
    ''')
    print(f'Tables after: {len(tables)}')
    for t in tables:
        print(f'  {t["tablename"]}')
    
    await conn.close()

asyncio.run(test_drop())
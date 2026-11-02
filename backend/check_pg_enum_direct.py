import asyncpg
import asyncio

async def check_pg_enum_direct():
    conn = await asyncpg.connect('postgresql://postgres:postgres@localhost:5432/vcos_test')
    
    # Check pg_enum directly with a simple query
    result = await conn.fetch('SELECT * FROM pg_enum')
    print(f'pg_enum rows: {len(result)}')
    for row in result:
        print(f'  {row}')
    
    # Check pg_type for autonomy_event_type
    types = await conn.fetch('''
        SELECT typname, typtype, oid, typnamespace::regnamespace
        FROM pg_type
        WHERE typname LIKE '%autonomy%'
    ''')
    print(f'autonomy types in pg_type: {len(types)}')
    for t in types:
        print(f'  {t}')
    
    # Check pg_enum for any enum with 'verified' label
    enums = await conn.fetch('''
        SELECT enumtypid, enumlabel, enumsortorder
        FROM pg_enum
        WHERE enumlabel = 'verified'
    ''')
    print(f'enums with verified label: {len(enums)}')
    for e in enums:
        print(f'  {e}')
    
    await conn.close()

asyncio.run(check_pg_enum_direct())
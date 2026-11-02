import asyncpg
import asyncio

async def check_oid():
    conn = await asyncpg.connect('postgresql://postgres:postgres@localhost:5432/vcos_test')
    
    # Check if there's a type with oid 8590508
    types = await conn.fetch('''
        SELECT typname, typtype, oid, typnamespace::regnamespace
        FROM pg_type
        WHERE oid = 8590508
    ''')
    print(f'Type with oid 8590508: {types}')
    
    # Check pg_enum for enumtypid 8590508
    enums = await conn.fetch('''
        SELECT enumtypid, enumlabel, enumsortorder
        FROM pg_enum
        WHERE enumtypid = 8590508
    ''')
    print(f'Enums with enumtypid 8590508: {len(enums)}')
    for e in enums:
        print(f'  {e}')
    
    await conn.close()

asyncio.run(check_oid())
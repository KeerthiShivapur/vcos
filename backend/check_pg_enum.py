import asyncpg
import asyncio

async def check_pg_enum():
    conn = await asyncpg.connect('postgresql://postgres:postgres@localhost:5432/vcos_test')
    # Check pg_enum directly
    enums = await conn.fetch('''
        SELECT enumtypid, enumlabel, enumsortorder
        FROM pg_enum
        ORDER BY enumtypid, enumsortorder
    ''')
    print(f'Found {len(enums)} enum labels in pg_enum')
    for enum in enums:
        if 'verified' in enum['enumlabel'] or 'autonomy' in str(enum['enumtypid']):
            print(f'  enumtypid={enum["enumtypid"]}, enumlabel={enum["enumlabel"]}, enumsortorder={enum["enumsortorder"]}')
    
    # Check pg_type for autonomy_event_type
    types = await conn.fetch('''
        SELECT t.typname, t.typtype, t.oid, n.nspname
        FROM pg_type t 
        JOIN pg_namespace n ON n.oid = t.typnamespace 
        WHERE t.typname LIKE '%autonomy%' OR t.typname LIKE '%verified%'
    ''')
    for typ in types:
        print(f'Type: {typ["typname"]}, typtype: {typ["typtype"]}, oid: {typ["oid"]}, schema: {typ["nspname"]}')
    
    await conn.close()

asyncio.run(check_pg_enum())
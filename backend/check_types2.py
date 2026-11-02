import asyncpg
import asyncio

async def check_enums():
    conn = await asyncpg.connect('postgresql://postgres:postgres@localhost:5432/vcos_test')
    # Check all types in all schemas
    types = await conn.fetch('''
        SELECT t.typname, t.typtype, n.nspname
        FROM pg_type t 
        JOIN pg_namespace n ON n.oid = t.typnamespace 
    ''')
    for typ in types:
        if 'autonomy' in typ['typname'] or 'verified' in typ['typname']:
            print(f'Type: {typ["typname"]}, typtype: {typ["typtype"]}, schema: {typ["nspname"]}')
    await conn.close()

asyncio.run(check_enums())
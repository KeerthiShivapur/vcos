import asyncpg
import asyncio

async def check_enums():
    for db_name in ['postgres', 'vcos_test', 'template1']:
        try:
            conn = await asyncpg.connect(f'postgresql://postgres:postgres@localhost:5432/{db_name}')
            # Check all types in all schemas
            types = await conn.fetch('''
                SELECT t.typname, t.typtype, n.nspname
                FROM pg_type t 
                JOIN pg_namespace n ON n.oid = t.typnamespace 
                WHERE t.typname LIKE '%autonomy%' OR t.typname LIKE '%verified%'
            ''')
            for typ in types:
                print(f'DB: {db_name}, Type: {typ["typname"]}, typtype: {typ["typtype"]}, schema: {typ["nspname"]}')
            await conn.close()
        except Exception as e:
            print(f'Error connecting to {db_name}: {e}')

asyncio.run(check_enums())
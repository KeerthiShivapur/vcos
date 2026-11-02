import asyncpg
import asyncio

async def check_all():
    print("Starting check...")
    for db_name in ['postgres', 'vcos_test', 'template1']:
        print(f'Checking {db_name}...')
        try:
            conn = await asyncpg.connect(f'postgresql://postgres:postgres@localhost:5432/{db_name}')
            print(f'  Connected to {db_name}')
            # Check all enums
            enums = await conn.fetch('''
                SELECT t.typname, t.typtype, n.nspname, t.oid
                FROM pg_type t 
                JOIN pg_namespace n ON n.oid = t.typnamespace 
                WHERE t.typtype = 'e'
                ORDER BY n.nspname, t.typname
            ''')
            print(f'  Found {len(enums)} enums')
            if enums:
                print(f'=== {db_name} ===')
                for enum in enums:
                    print(f'  Enum: {enum["typname"]} (oid={enum["oid"]}), schema: {enum["nspname"]}')
            else:
                print(f'=== {db_name} === (no enums)')
            await conn.close()
        except Exception as e:
            print(f'Error connecting to {db_name}: {e}')

    print("Done")

import asyncio
asyncio.run(check_all())
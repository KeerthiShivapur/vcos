import asyncpg
import asyncio

async def check_all():
    conn = await asyncpg.connect('postgresql://postgres:postgres@localhost:5432/vcos_test')
    
    # Check pg_class for autonomy_event_type
    classes = await conn.fetch('''
        SELECT relname, relkind, relnamespace::regnamespace
        FROM pg_class
        WHERE relname LIKE '%autonomy%'
    ''')
    print(f'pg_class matches: {len(classes)}')
    for c in classes:
        print(f'  {c}')
    
    # Check pg_type
    types = await conn.fetch('''
        SELECT typname, typtype, oid, typnamespace::regnamespace
        FROM pg_type
        WHERE typname LIKE '%autonomy%'
    ''')
    print(f'pg_type matches: {len(types)}')
    for t in types:
        print(f'  {t}')
    
    # Check pg_enum
    enums = await conn.fetch('SELECT * FROM pg_enum')
    print(f'pg_enum rows: {len(enums)}')
    
    # Check pg_depend
    deps = await conn.fetch('''
        SELECT * FROM pg_depend WHERE objid IN (SELECT oid FROM pg_type WHERE typname LIKE '%autonomy%')
    ''')
    print(f'pg_depend matches: {len(deps)}')
    
    await conn.close()

asyncio.run(check_all())
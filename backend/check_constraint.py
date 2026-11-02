import asyncpg
import asyncio

async def check_constraint():
    conn = await asyncpg.connect('postgresql://postgres:postgres@localhost:5432/vcos_test')
    
    # Check the constraint
    constraints = await conn.fetch('''
        SELECT conname, contype, conrelid::regclass
        FROM pg_constraint
        WHERE conname = 'pg_enum_typid_label_index'
    ''')
    print(f'Constraint: {constraints}')
    
    # Check pg_index
    indexes = await conn.fetch('''
        SELECT indexrelid::regclass, indrelid::regclass
        FROM pg_index
        WHERE indexrelid = 'pg_enum_typid_label_index'::regclass
    ''')
    print(f'Index: {indexes}')
    
    # Check pg_enum structure
    cols = await conn.fetch('''
        SELECT attname, atttypid::regtype
        FROM pg_attribute
        WHERE attrelid = 'pg_enum'::regclass
    ''')
    print(f'pg_enum columns: {cols}')
    
    await conn.close()

asyncio.run(check_constraint())
import asyncio
import asyncpg

async def test():
    conn = await asyncpg.connect('postgresql://vcos:vcos@localhost:5432/vcos_test')
    # Check current schema
    result = await conn.fetchval('SELECT current_schema()')
    print(f'current_schema: {result}')
    
    # Check search_path
    result = await conn.fetchval('SHOW search_path')
    print(f'search_path: {result}')
    
    # Try to create a table with explicit schema
    try:
        await conn.execute('CREATE TABLE public.test_table (id INT)')
        print('Table created in public schema')
    except Exception as e:
        print(f'Table error: {e}')
    
    # Try to create an enum with explicit schema
    try:
        await conn.execute("CREATE TYPE public.test_enum AS ENUM ('a', 'b')")
        print('Enum created in public schema')
    except Exception as e:
        print(f'Enum error: {e}')
    
    await conn.close()

asyncio.run(test())
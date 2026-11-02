import asyncio
import asyncpg

async def test():
    # Connect with options parameter
    conn = await asyncpg.connect('postgresql://vcos:vcos@localhost:5432/vcos_test?options=-csearch_path%3Dpublic')
    
    # Check current schema
    result = await conn.fetchval('SELECT current_schema()')
    print(f'current_schema: {result}')
    
    # Check search_path
    result = await conn.fetchval('SHOW search_path')
    print(f'search_path: {result}')
    
    # Try to create a table without explicit schema
    try:
        await conn.execute('CREATE TABLE test_table3 (id INT)')
        print('Table created without explicit schema')
    except Exception as e:
        print(f'Table error: {e}')
    
    # Try to create an enum without explicit schema
    try:
        await conn.execute("CREATE TYPE test_enum3 AS ENUM ('a', 'b')")
        print('Enum created without explicit schema')
    except Exception as e:
        print(f'Enum error: {e}')
    
    await conn.close()

asyncio.run(test())
import asyncio
import asyncpg

async def test():
    conn = await asyncpg.connect('postgresql://vcos:vcos@localhost:5432/vcos_test')
    await conn.execute('SET search_path TO public')
    result = await conn.fetchval('SHOW search_path')
    print(f'search_path: {result}')
    
    # Try to create a simple table
    await conn.execute('CREATE TABLE IF NOT EXISTS test_table (id INT)')
    print('Table created')
    
    # Try to create an enum
    try:
        await conn.execute("CREATE TYPE test_enum AS ENUM ('a', 'b')")
        print('Enum created')
    except Exception as e:
        print(f'Enum error: {e}')
    
    await conn.close()

asyncio.run(test())
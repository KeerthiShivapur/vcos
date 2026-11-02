import asyncio
import asyncpg

async def test():
    conn = await asyncpg.connect('postgresql://vcos:vcos@localhost:5432/vcos_test')
    await conn.execute('SET search_path TO public')
    result = await conn.fetchval('SHOW search_path')
    print(f'Search path: {result}')
    
    result = await conn.fetchval('SELECT current_schema()')
    print(f'Current schema: {result}')
    
    result = await conn.fetchval('SELECT current_setting(\'search_path\')')
    print(f'Search path setting: {result}')
    
    await conn.close()

asyncio.run(test())
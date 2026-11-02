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
    
    # Check user
    result = await conn.fetchval('SELECT current_user')
    print(f'current_user: {result}')
    
    # Check if public schema exists
    result = await conn.fetchval("SELECT count(*) FROM information_schema.schemata WHERE schema_name = 'public'")
    print(f'public schema exists: {result}')
    
    await conn.close()

asyncio.run(test())
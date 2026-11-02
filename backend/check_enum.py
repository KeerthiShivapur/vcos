import asyncio
import asyncpg

async def test():
    conn = await asyncpg.connect('postgresql://vcos:vcos@localhost:5432/vcos_test')
    await conn.execute('SET search_path TO public')
    
    result = await conn.fetchval("SELECT nspname FROM pg_type t JOIN pg_namespace n ON t.typnamespace = n.oid WHERE t.typname = 'autonomy_risk_class'")
    print(f'Enum schema: {result}')
    
    result = await conn.fetchval("SELECT count(*) FROM pg_type WHERE typname = 'autonomy_risk_class'")
    print(f'Enum count: {result}')
    
    await conn.close()

asyncio.run(test())
import asyncio
import asyncpg

async def test():
    conn = await asyncpg.connect('postgresql://vcos:vcos@localhost:5432/vcos_test')
    await conn.execute('SET search_path TO public')
    
    result = await conn.fetchval("SELECT count(*) FROM pg_type WHERE typname = 'autonomy_risk_class'")
    print(f'Enum count: {result}')
    
    await conn.execute('DROP TYPE IF EXISTS autonomy_risk_class')
    print('Dropped enum if existed')
    
    try:
        await conn.execute("CREATE TYPE autonomy_risk_class AS ENUM ('observe_only', 'propose_only', 'auto_execute_reversible', 'auto_execute_within_policy', 'human_approval_required', 'privileged_human_approval', 'prohibited')")
        print('Enum created successfully!')
    except Exception as e:
        print(f'Error: {e}')
    
    await conn.close()

asyncio.run(test())
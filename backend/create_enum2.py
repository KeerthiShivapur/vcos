import asyncio
import asyncpg

async def test():
    conn = await asyncpg.connect('postgresql://vcos:vcos@localhost:5432/vcos_test')
    await conn.execute('SET search_path TO public')
    
    result = await conn.fetchval("SELECT has_schema_privilege(current_user, 'public', 'CREATE')")
    print(f'Has CREATE on public: {result}')
    
    result = await conn.fetchval("SELECT count(*) FROM pg_type WHERE typname = 'autonomy_risk_class'")
    print(f'autonomy_risk_class exists: {result}')
    
    # Try creating the enum
    try:
        await conn.execute("CREATE TYPE autonomy_risk_class AS ENUM ('observe_only', 'propose_only', 'auto_execute_reversible', 'auto_execute_within_policy', 'human_approval_required', 'privileged_human_approval', 'prohibited')")
        print('Enum created successfully!')
    except Exception as e:
        print(f'Error creating enum: {e}')
    
    await conn.close()

asyncio.run(test())
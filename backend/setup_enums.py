import asyncio
import asyncpg

async def setup_enums():
    conn = await asyncpg.connect('postgresql://postgres:postgres@localhost:5432/vcos_test')
    await conn.execute('SET search_path TO public')
    
    # Drop if exists
    await conn.execute('DROP TYPE IF EXISTS autonomy_risk_class CASCADE')
    print('Dropped enum if existed')
    
    # Create the enum
    await conn.execute("""
        CREATE TYPE autonomy_risk_class AS ENUM (
            'observe_only', 'propose_only', 'auto_execute_reversible',
            'auto_execute_within_policy', 'human_approval_required',
            'privileged_human_approval', 'prohibited'
        )
    """)
    print('Enum created successfully!')
    
    # Grant permissions
    await conn.execute('GRANT ALL ON TYPE autonomy_risk_class TO vcos')
    print('Granted permissions')
    
    # Create second enum
    await conn.execute('DROP TYPE IF EXISTS autonomy_risk_class_eval CASCADE')
    await conn.execute("""
        CREATE TYPE autonomy_risk_class_eval AS ENUM (
            'observe_only', 'propose_only', 'auto_execute_reversible',
            'auto_execute_within_policy', 'human_approval_required',
            'privileged_human_approval', 'prohibited'
        )
    """)
    await conn.execute('GRANT ALL ON TYPE autonomy_risk_class_eval TO vcos')
    print('Second enum created and granted')
    
    await conn.close()
    print('Enums setup complete')

import asyncio
asyncio.run(setup_enums())
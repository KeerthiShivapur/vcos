import asyncpg
import asyncio

async def test_create():
    conn = await asyncpg.connect('postgresql://postgres:postgres@localhost:5432/vcos_test')
    
    # Start a transaction
    tr = conn.transaction()
    await tr.start()
    
    # Try to create the enum
    try:
        await conn.execute("""CREATE TYPE autonomy_event_type AS ENUM ('discovered', 'eligibility_evaluated', 'proposed', 'evidence_validated', 'governance_evaluated', 'authorization_required', 'authorized', 'committed', 'executing', 'executed', 'outcome_observed', 'verified', 'assessed', 'learned', 'rejected', 'cancelled', 'failed', 'blocked', 'superseded', 'policy_evaluated', 'evidence_gathered', 'precondition_checked', 'external_operation_started', 'external_operation_completed', 'external_operation_failed', 'outcome_recorded', 'verified', 'assessed', 'learned')""")
        print('Create: Success')
    except Exception as e:
        print(f'Create error: {e}')
    
    # Check pg_enum immediately after
    enums = await conn.fetch('SELECT enumtypid, enumlabel FROM pg_enum WHERE enumlabel = \'verified\'')
    print(f'pg_enum rows with verified: {len(enums)}')
    for e in enums:
        print(f'  enumtypid={e["enumtypid"]}, enumlabel={e["enumlabel"]}')
    
    # Check all pg_enum
    all_enums = await conn.fetch('SELECT enumtypid, enumlabel FROM pg_enum')
    print(f'All pg_enum rows: {len(all_enums)}')
    for e in all_enums:
        print(f'  enumtypid={e["enumtypid"]}, enumlabel={e["enumlabel"]}')
    
    await tr.rollback()
    print('Transaction rolled back')
    
    # Check after rollback
    enums = await conn.fetch('SELECT enumtypid, enumlabel FROM pg_enum WHERE enumlabel = \'verified\'')
    print(f'pg_enum rows with verified after rollback: {len(enums)}')
    
    await conn.close()

asyncio.run(test_create())
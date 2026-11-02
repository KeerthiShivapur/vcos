import asyncpg
import asyncio

async def test_tx():
    conn = await asyncpg.connect('postgresql://postgres:postgres@localhost:5432/vcos_test')
    
    # Start a transaction
    tr = conn.transaction()
    await tr.start()
    
    try:
        await conn.execute("""CREATE TYPE autonomy_event_type AS ENUM ('discovered', 'eligibility_evaluated', 'proposed', 'evidence_validated', 'governance_evaluated', 'authorization_required', 'authorized', 'committed', 'executing', 'executed', 'outcome_observed', 'verified', 'assessed', 'learned', 'rejected', 'cancelled', 'failed', 'blocked', 'superseded', 'policy_evaluated', 'evidence_gathered', 'precondition_checked', 'external_operation_started', 'external_operation_completed', 'external_operation_failed', 'outcome_recorded', 'verified', 'assessed', 'learned')""")
        print('Create in transaction: Success')
    except Exception as e:
        print(f'Create in transaction error: {e}')
    
    # Check pg_enum within transaction
    enums = await conn.fetch('SELECT * FROM pg_enum')
    print(f'pg_enum rows in transaction: {len(enums)}')
    for enum in enums:
        print(f'  {enum}')
    
    await tr.rollback()
    print('Transaction rolled back')
    
    # Check after rollback
    enums = await conn.fetch('SELECT * FROM pg_enum')
    print(f'pg_enum rows after rollback: {len(enums)}')
    
    await conn.close()

asyncio.run(test_tx())
import asyncpg
import asyncio

async def test_drop_and_recreate():
    conn = await asyncpg.connect('postgresql://postgres:postgres@localhost:5432/vcos_test')
    
    # Drop the type if it exists
    try:
        await conn.execute("DROP TYPE IF EXISTS autonomy_event_type CASCADE")
        print('Dropped existing type')
    except Exception as e:
        print(f'Drop error: {e}')
    
    # Try to create the type with all values at once
    try:
        await conn.execute("""CREATE TYPE autonomy_event_type AS ENUM ('discovered', 'eligibility_evaluated', 'proposed', 'evidence_validated', 'governance_evaluated', 'authorization_required', 'authorized', 'committed', 'executing', 'executed', 'outcome_observed', 'verified', 'assessed', 'learned', 'rejected', 'cancelled', 'failed', 'blocked', 'superseded', 'policy_evaluated', 'evidence_gathered', 'precondition_checked', 'external_operation_started', 'external_operation_completed', 'external_operation_failed', 'outcome_recorded')""")
        print('Create all at once: Success')
    except Exception as e:
        print(f'Create all at once error: {e}')
    
    await conn.close()

asyncio.run(test_drop_and_recreate())
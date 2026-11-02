import asyncpg
import asyncio

async def test_full():
    conn = await asyncpg.connect('postgresql://postgres:postgres@localhost:5432/vcos_test')
    
    # Try the full set in original order
    try:
        await conn.execute("DROP TYPE IF EXISTS autonomy_event_type CASCADE")
        await conn.execute("""CREATE TYPE autonomy_event_type AS ENUM ('discovered', 'eligibility_evaluated', 'proposed', 'evidence_validated', 'governance_evaluated', 'authorization_required', 'authorized', 'committed', 'executing', 'executed', 'outcome_observed', 'verified', 'assessed', 'learned', 'rejected', 'cancelled', 'failed', 'blocked', 'superseded', 'policy_evaluated', 'evidence_gathered', 'precondition_checked', 'external_operation_started', 'external_operation_completed', 'external_operation_failed', 'outcome_recorded', 'verified', 'assessed', 'learned')""")
        print('Full set original order: Success')
    except Exception as e:
        print(f'Full set original order error: {e}')
    
    await conn.close()

asyncio.run(test_full())
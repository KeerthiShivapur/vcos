import asyncpg
import asyncio

async def test_subsets():
    conn = await asyncpg.connect('postgresql://postgres:postgres@localhost:5432/vcos_test')
    
    # Test 1: First half
    try:
        await conn.execute("DROP TYPE IF EXISTS test_enum_1 CASCADE")
        await conn.execute("""CREATE TYPE test_enum_1 AS ENUM ('discovered', 'eligibility_evaluated', 'proposed', 'evidence_validated', 'governance_evaluated', 'authorization_required', 'authorized', 'committed', 'executing', 'executed', 'outcome_observed')""")
        print('Test 1 (first 11): Success')
    except Exception as e:
        print(f'Test 1 error: {e}')
    
    # Test 2: Second half with verified
    try:
        await conn.execute("DROP TYPE IF EXISTS test_enum_2 CASCADE")
        await conn.execute("""CREATE TYPE test_enum_2 AS ENUM ('verified', 'assessed', 'learned', 'rejected', 'cancelled', 'failed', 'blocked', 'superseded', 'policy_evaluated', 'evidence_gathered', 'precondition_checked', 'external_operation_started', 'external_operation_completed', 'external_operation_failed', 'outcome_recorded')""")
        print('Test 2 (second 14 with verified first): Success')
    except Exception as e:
        print(f'Test 2 error: {e}')
    
    # Test 3: All but verified
    try:
        await conn.execute("DROP TYPE IF EXISTS test_enum_3 CASCADE")
        await conn.execute("""CREATE TYPE test_enum_3 AS ENUM ('discovered', 'eligibility_evaluated', 'proposed', 'evidence_validated', 'governance_evaluated', 'authorization_required', 'authorized', 'committed', 'executing', 'executed', 'outcome_observed', 'assessed', 'learned', 'rejected', 'cancelled', 'failed', 'blocked', 'superseded', 'policy_evaluated', 'evidence_gathered', 'precondition_checked', 'external_operation_started', 'external_operation_completed', 'external_operation_failed', 'outcome_recorded')""")
        print('Test 3 (all but verified): Success')
    except Exception as e:
        print(f'Test 3 error: {e}')
    
    # Test 4: Just verified
    try:
        await conn.execute("DROP TYPE IF EXISTS test_enum_4 CASCADE")
        await conn.execute("""CREATE TYPE test_enum_4 AS ENUM ('verified')""")
        print('Test 4 (just verified): Success')
    except Exception as e:
        print(f'Test 4 error: {e}')
    
    # Test 5: verified in middle
    try:
        await conn.execute("DROP TYPE IF EXISTS test_enum_5 CASCADE")
        await conn.execute("""CREATE TYPE test_enum_5 AS ENUM ('discovered', 'verified', 'assessed')""")
        print('Test 5 (verified in middle): Success')
    except Exception as e:
        print(f'Test 5 error: {e}')
    
    await conn.close()

asyncio.run(test_subsets())
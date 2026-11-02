import asyncpg
import asyncio

async def test_create_step_by_step():
    conn = await asyncpg.connect('postgresql://postgres:postgres@localhost:5432/vcos_test')
    
    # Step 1: Create the type without enum values
    try:
        await conn.execute("CREATE TYPE autonomy_event_type AS ENUM ('discovered')")
        print('Step 1 - Create type with one value: Success')
    except Exception as e:
        print(f'Step 1 error: {e}')
    
    # Check pg_enum
    enums = await conn.fetch('SELECT enumtypid, enumlabel FROM pg_enum WHERE enumlabel = \'discovered\'')
    print(f'pg_enum rows with discovered: {len(enums)}')
    for e in enums:
        print(f'  enumtypid={e["enumtypid"]}, enumlabel={e["enumlabel"]}')
    
    # Step 2: Add more values
    try:
        await conn.execute("ALTER TYPE autonomy_event_type ADD VALUE 'eligibility_evaluated'")
        print('Step 2 - Add eligibility_evaluated: Success')
    except Exception as e:
        print(f'Step 2 error: {e}')
    
    # Check pg_enum
    enums = await conn.fetch('SELECT enumtypid, enumlabel FROM pg_enum WHERE enumlabel = \'eligibility_evaluated\'')
    print(f'pg_enum rows with eligibility_evaluated: {len(enums)}')
    for e in enums:
        print(f'  enumtypid={e["enumtypid"]}, enumlabel={e["enumlabel"]}')
    
    # Step 3: Add verified
    try:
        await conn.execute("ALTER TYPE autonomy_event_type ADD VALUE 'verified'")
        print('Step 3 - Add verified: Success')
    except Exception as e:
        print(f'Step 3 error: {e}')
    
    # Check pg_enum
    enums = await conn.fetch('SELECT enumtypid, enumlabel FROM pg_enum WHERE enumlabel = \'verified\'')
    print(f'pg_enum rows with verified: {len(enums)}')
    for e in enums:
        print(f'  enumtypid={e["enumtypid"]}, enumlabel={e["enumlabel"]}')
    
    await conn.close()

asyncio.run(test_create_step_by_step())
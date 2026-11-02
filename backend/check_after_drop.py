import asyncpg
import asyncio

async def check_after_drop():
    conn = await asyncpg.connect('postgresql://postgres:postgres@localhost:5432/vcos_gate7')
    tables = await conn.fetch("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
    print('Tables after schema recreation:', [t['tablename'] for t in tables])
    
    constraints = await conn.fetch("""
        SELECT conname, conrelid::regclass as table_name 
        FROM pg_constraint 
        WHERE conname = 'uq_dc_fp_exact_once'
    """)
    print('Constraints:', [(c['conname'], c['table_name']) for c in constraints])
    await conn.close()

asyncio.run(check_after_drop())
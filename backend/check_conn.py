import asyncio
import asyncpg

async def check():
    conn = await asyncpg.connect('postgresql://postgres:postgres@localhost:5432/vcos_test')
    r = await conn.fetch("""
        SELECT count(*) as total, 
               count(*) filter (where state='idle in transaction') as idle_in_tx 
        FROM pg_stat_activity 
        WHERE datname='vcos_test'
    """)
    print(dict(r[0]))
    await conn.close()

asyncio.run(check())
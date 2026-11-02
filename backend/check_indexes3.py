import asyncpg
import asyncio

async def check():
    conn = await asyncpg.connect('postgresql://postgres:postgres@localhost:5432/vcos_test')
    indexes = await conn.fetch("SELECT indexname FROM pg_indexes WHERE schemaname = 'public' AND tablename = 'canonical_metrics'")
    print('Canonical_metrics indexes:', [i['indexname'] for i in indexes])
    await conn.close()

asyncio.run(check())
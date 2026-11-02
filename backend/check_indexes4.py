import asyncpg
import asyncio

async def check():
    conn = await asyncpg.connect('postgresql://postgres:postgres@localhost:5432/vcos_test')
    indexes = await conn.fetch("SELECT indexname FROM pg_indexes WHERE schemaname = 'public' AND tablename = 'metric_observations'")
    print('Metric_observations indexes:', [i['indexname'] for i in indexes])
    await conn.close()

asyncio.run(check())
import asyncio
import asyncpg

async def add_fingerprint_column():
    conn = await asyncpg.connect('postgresql://postgres:postgres@localhost:5432/vcos_test')
    try:
        await conn.execute('ALTER TABLE company_goals ADD COLUMN IF NOT EXISTS fingerprint VARCHAR(64) DEFAULT \'\'')
        print('Added fingerprint column to company_goals')
    except Exception as e:
        print(f'Error: {e}')
    finally:
        await conn.close()

asyncio.run(add_fingerprint_column())
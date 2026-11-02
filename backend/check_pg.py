import asyncio
import os
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

async def check_pg():
    url = os.environ.get('TEST_DATABASE_URL', 'postgresql+asyncpg://vcos:vcos@localhost:5432/vcos_test')
    print(f'Testing connection to: {url}')
    try:
        engine = create_async_engine(url, pool_size=1, max_overflow=0)
        async with engine.begin() as conn:
            result = await conn.execute(text('SELECT version()'))
            version = result.scalar()
            print(f'PostgreSQL connected: {version}')
            result = await conn.execute(text("SELECT table_name FROM information_schema.tables WHERE table_schema='public'"))
            tables = [row[0] for row in result]
            print(f'Tables found: {len(tables)}')
            for t in sorted(tables)[:20]:
                print(f'  {t}')
        await engine.dispose()
    except Exception as e:
        print(f'PostgreSQL connection failed: {e}')

asyncio.run(check_pg())
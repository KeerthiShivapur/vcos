import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

async def check_sizes():
    engine = create_async_engine('postgresql+asyncpg://postgres:postgres@localhost:5432/vcos_test', poolclass=None)
    async with engine.begin() as conn:
        result = await conn.execute(text("""
            SELECT 
                schemaname, 
                relname, 
                pg_size_pretty(pg_total_relation_size(relid)) as size
            FROM pg_stat_user_tables
            ORDER BY pg_total_relation_size(relid) DESC
            LIMIT 20
        """))
        for row in result:
            print(f'{row.schemaname}.{row.relname}: {row.size}')
    await engine.dispose()

asyncio.run(check_sizes())
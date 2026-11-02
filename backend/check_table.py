import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

async def check_table():
    engine = create_async_engine('postgresql+asyncpg://postgres:postgres@localhost:5432/vcos_test', poolclass=None)
    async with engine.begin() as conn:
        query = """
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = 'external_unknown_states'
            ORDER BY ordinal_position
        """
        result = await conn.execute(text(query))
        for row in result:
            print(row)
    await engine.dispose()

asyncio.run(check_table())
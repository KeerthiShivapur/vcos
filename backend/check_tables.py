import asyncio
from app.db.database import get_engine
from sqlalchemy import inspect

async def main():
    engine = get_engine()
    async with engine.begin() as conn:
        def get_tables(sync_conn):
            return inspect(sync_conn).get_table_names()
        tables = await conn.run_sync(get_tables)
        print('Tables in DB:', sorted(tables))

asyncio.run(main())
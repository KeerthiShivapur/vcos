from app.db.database import SessionLocal
from sqlalchemy import text
import asyncio

async def test():
    async with SessionLocal() as db:
        result = await db.execute(text("SELECT rolname, rolsuper, rolbypassrls FROM pg_roles WHERE rolname NOT LIKE 'pg_%' ORDER BY rolname"))
        for row in result.fetchall():
            print(f'Role: {row.rolname}, super: {row.rolsuper}, bypassrls: {row.rolbypassrls}')

asyncio.run(test())
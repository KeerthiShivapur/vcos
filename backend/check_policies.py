from app.db.database import SessionLocal
from sqlalchemy import text
import asyncio

async def test():
    async with SessionLocal() as db:
        # Check policies on employees
        result = await db.execute(text("""
            SELECT schemaname, tablename, policyname, cmd, qual 
            FROM pg_policies 
            WHERE tablename = 'employees'
        """))
        print('Policies on employees:')
        for row in result.fetchall():
            print(f'  {row.policyname} ({row.cmd}): {row.qual}')

asyncio.run(test())
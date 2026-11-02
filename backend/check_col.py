from app.db.database import SessionLocal
from sqlalchemy import text
import asyncio

async def check():
    async with SessionLocal() as db:
        result = await db.execute(text("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = 'academies' AND column_name = 'organization_id'
        """))
        print(result.fetchall())

asyncio.run(check())
import asyncio
from sqlalchemy import text
from app.db.database import SessionLocal

async def test():
    async with SessionLocal() as db:
        result = await db.execute(text("""
            SELECT column_name, data_type, character_maximum_length 
            FROM information_schema.columns 
            WHERE table_name = 'canonical_company_health' 
            ORDER BY ordinal_position
        """))
        for row in result:
            print(row)

asyncio.run(test())
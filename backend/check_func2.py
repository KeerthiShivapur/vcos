from app.db.database import SessionLocal
from sqlalchemy import text
import asyncio

async def test():
    async with SessionLocal() as db:
        await db.execute(text("SET ROLE vcos"))
        await db.commit()
        
        # Check if function exists
        result = await db.execute(text("""
            SELECT proname FROM pg_proc 
            WHERE proname = 'current_organization_id' AND pronamespace = 'public'::regnamespace
        """))
        func = result.fetchone()
        print(f'Function exists: {func}')
        
        if func:
            result = await db.execute(text("SELECT current_organization_id()"))
            val = result.scalar()
            print(f'current_organization_id(): {val}')

asyncio.run(test())
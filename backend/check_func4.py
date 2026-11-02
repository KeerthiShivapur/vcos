from app.db.database import SessionLocal
from sqlalchemy import text
import asyncio

async def test():
    async with SessionLocal() as db:
        await db.execute(text("SET ROLE vcos"))
        await db.commit()
        
        # Check search_path
        result = await db.execute(text("SHOW search_path"))
        sp = result.fetchone()
        print(f'search_path: {sp}')
        
        # Check function visibility
        result = await db.execute(text("""
            SELECT p.proname, n.nspname 
            FROM pg_proc p
            JOIN pg_namespace n ON p.pronamespace = n.oid
            WHERE p.proname = 'current_organization_id'
        """))
        funcs = result.fetchall()
        print(f'Function visibility: {funcs}')
        
        # Try to call the function
        try:
            result = await db.execute(text("SELECT current_organization_id()"))
            val = result.scalar()
            print(f'current_organization_id(): {val}')
        except Exception as e:
            print(f'Error calling function: {e}')

asyncio.run(test())
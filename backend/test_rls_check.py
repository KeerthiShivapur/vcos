from app.db.database import SessionLocal
from sqlalchemy import text
import asyncio

async def test():
    async with SessionLocal() as db:
        # Check RLS is enabled on employees
        result = await db.execute(text("""
            SELECT schemaname, tablename, rowsecurity 
            FROM pg_tables 
            WHERE tablename = 'employees'
        """))
        print('RLS enabled on employees:', result.fetchall())
        
        # Check policies on employees
        result = await db.execute(text("""
            SELECT schemaname, tablename, policyname, cmd, qual 
            FROM pg_policies 
            WHERE tablename = 'employees'
        """))
        print('Policies on employees:')
        for row in result.fetchall():
            print(f'  {row}')
            
        # Test current_organization_id function
        result = await db.execute(text("SELECT current_organization_id()"))
        print('current_organization_id() without context:', result.scalar())
        
        # Set context and test
        await db.execute(text("SELECT set_config('app.current_organization_id', '12345678-1234-1234-1234-123456789012', false)"))
        result = await db.execute(text("SELECT current_organization_id()"))
        print('current_organization_id() with context:', result.scalar())

asyncio.run(test())
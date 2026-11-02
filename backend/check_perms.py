from app.db.database import SessionLocal
from sqlalchemy import text
import asyncio

async def test():
    async with SessionLocal() as db:
        await db.execute(text("SET ROLE vcos"))
        await db.commit()
        
        # Check function permissions
        result = await db.execute(text("""
            SELECT p.proacl FROM pg_proc p
            JOIN pg_namespace n ON p.pronamespace = n.oid
            WHERE p.proname = 'current_organization_id' AND n.nspname = 'public'
        """))
        acl = result.fetchone()
        print(f'Function ACL: {acl}')
        
        # Check if vcos has execute permission
        result = await db.execute(text("""
            SELECT has_function_privilege('vcos', 'public.current_organization_id()', 'EXECUTE')
        """))
        has_priv = result.scalar()
        print(f'vcos has EXECUTE on current_organization_id(): {has_priv}')

asyncio.run(test())
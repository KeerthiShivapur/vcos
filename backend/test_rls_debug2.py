from app.db.database import SessionLocal
from sqlalchemy import text
import asyncio

async def test():
    async with SessionLocal() as db:
        # Check current user and RLS status
        result = await db.execute(text("SELECT current_user, session_user"))
        print(f'Current user: {result.fetchone()}')
        
        # Check if RLS is enabled on employees
        result = await db.execute(text("SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname = 'employees'"))
        print(f'Employees table RLS: {result.fetchone()}')
        
        # Check policies
        result = await db.execute(text("""
            SELECT polname, polcmd, pg_get_expr(polqual, polrelid) as qual
            FROM pg_policy
            WHERE polrelid = 'employees'::regclass
        """))
        for row in result.fetchall():
            print(f'Policy: {row.polname}, cmd: {row.polcmd}, qual: {row.qual}')
        
        # Check if RLS is enforced for current user
        result = await db.execute(text("SELECT has_table_privilege(current_user, 'employees', 'SELECT')"))
        print(f'Has SELECT on employees: {result.scalar()}')
        
        # Check if current_user bypasses RLS
        result = await db.execute(text("SELECT rolbypassrls FROM pg_roles WHERE rolname = current_user"))
        print(f'Bypass RLS: {result.scalar()}')
        
        # Check current user's roles
        result = await db.execute(text("SELECT rolname, rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user"))
        print(f'Current user role: {result.fetchone()}')

asyncio.run(test())
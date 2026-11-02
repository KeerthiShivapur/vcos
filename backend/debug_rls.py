from app.db.database import SessionLocal
from sqlalchemy import text
import asyncio

async def test():
    async with SessionLocal() as db:
        await db.execute(text("SET ROLE vcos"))
        await db.commit()
        
        # Check if RLS is enforced for vcos role
        result = await db.execute(text("SELECT rolname, rolbypassrls FROM pg_roles WHERE rolname = 'vcos'"))
        print(f'vcos role: {result.fetchone()}')
        
        # Check table RLS settings
        result = await db.execute(text("SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname = 'employees'"))
        print(f'employees table RLS: {result.fetchone()}')
        
        # Check current_organization_id function
        await db.execute(text("SELECT set_config('app.current_organization_id', '12345678123412341234123456789012', false)"))
        result = await db.execute(text("SELECT current_organization_id()"))
        val = result.scalar()
        print(f'current_organization_id(): {val}')
        
        # Create organization first
        org_id = '11111111111111111111111111111111'
        await db.execute(text("""
            INSERT INTO organizations (id, name, slug, industry, country, timezone, language, currency, status, brand_primary_color, created_at, updated_at)
            VALUES (:id, :name, :slug, :industry, :country, :timezone, :language, :currency, :status, :color, NOW(), NOW())
        """), {"id": "11111111111111111111111111111111", "name": "Test Org", "slug": "test-org", "industry": "Tech", "country": "US", "timezone": "UTC", "language": "en", "currency": "USD", "status": "active", "color": "#4F46E5"})
        await db.commit()
        
        # Test insert and select
        org_id = '11111111111111111111111111111111'
        await db.execute(text("SET ROLE vcos"))
        await db.execute(text("SELECT set_config('app.current_organization_id', :org_id, false)"), {'org_id': '11111111111111111111111111111111'})
        await db.execute(text("INSERT INTO employees (id, organization_id, employee_number, first_name, last_name, email, designation, employment_type, status, timezone, expertise_score, profile_completion, created_at, updated_at) VALUES (:id, :org_id, :emp_num, :fn, :ln, :email, :desig, :et, :st, :tz, 0, 0, NOW(), NOW())"), {'id': 'test1', 'org_id': '11111111111111111111111111111111', 'emp_num': 'EMP-001', 'fn': 'Test', 'ln': 'User', 'email': 'test@test.com', 'desig': 'Eng', 'et': 'full_time', 'st': 'active', 'tz': 'UTC'})
        await db.commit()
        
        result = await db.execute(text("SELECT * FROM employees WHERE organization_id = :org_id"), {'org_id': '11111111111111111111111111111111'})
        rows = result.fetchall()
        print(f'Rows visible with correct context: {len(rows)}')
        
        # Try with different org context
        await db.execute(text("SET session_replication_role = origin"))  # bypass RLS
        await db.execute(text("INSERT INTO employees (id, organization_id, employee_number, first_name, last_name, email, designation, employment_type, status, timezone, expertise_score, profile_completion, created_at, updated_at) VALUES (:id, :org_id, :emp_num, :fn, :ln, :email, :desig, :et, :st, :tz, 0, 0, NOW(), NOW())"), {'id': 'test2', 'org_id': '22222222222222222222222222222222', 'emp_num': 'EMP-002', 'fn': 'Test2', 'ln': 'User2', 'email': 'test2@test.com', 'desig': 'Eng2', 'et': 'full_time', 'st': 'active', 'tz': 'UTC'})
        await db.commit()
        await db.execute(text("SET ROLE vcos"))
        await db.execute(text("SELECT set_config('app.current_organization_id', :org_id, false)"), {'org_id': '11111111111111111111111111111111'})
        result = await db.execute(text("SELECT * FROM employees"))
        rows = result.fetchall()
        print(f'Rows visible with org 1 context: {len(rows)}')
        
        # Cleanup
        await db.execute(text("DELETE FROM employees WHERE id IN (:id1, :id2)"), {'id1': 'test1', 'id2': 'test2'})
        await db.execute(text("DELETE FROM organizations WHERE id IN (:id1, :id2)"), {'id1': '11111111111111111111111111111111', 'id2': '22222222222222222222222222222222'})
        await db.commit()

asyncio.run(test())
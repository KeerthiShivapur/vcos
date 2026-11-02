from app.db.database import SessionLocal
from sqlalchemy import text
import asyncio
import uuid

async def test():
    async with SessionLocal() as db:
        # Set role to vcos
        await db.execute(text("SET ROLE vcos"))
        
        # Create two organizations
        org_a_id = uuid.uuid4().hex
        org_b_id = uuid.uuid4().hex
        
        # Insert organizations
        await db.execute(text("""
            INSERT INTO organizations (id, name, slug, industry, country, timezone, language, currency, status)
            VALUES (:id1, 'Org A', 'org-a-test', 'Technology', 'US', 'UTC', 'en', 'USD', 'active'),
                   (:id2, 'Org B', 'org-b-test', 'Technology', 'US', 'UTC', 'en', 'USD', 'active')
        """), {"id1": org_a_id, "id2": org_b_id})
        await db.commit()
        
        print(f"Created org_a: {org_a_id}")
        print(f"Created org_b: {org_b_id}")
        
        # Create users with explicit context
        # User for Org A
        await db.execute(text("SELECT set_config('app.current_organization_id', :org_id, false)"), {"org_id": org_a_id})
        await db.execute(text("""
            INSERT INTO users (id, organization_id, email, full_name, password_hash, status, role)
            VALUES (:id, :org_id, :email, :full_name, :password_hash, 'active', 'employee')
        """), {"id": uuid.uuid4().hex, "org_id": org_a_id, "email": f"admin-a-{uuid.uuid4().hex[:8]}@test.com", 
                "full_name": "Org A Admin", "password_hash": "test_hash"})
        await db.commit()
        
        # User for Org B
        await db.execute(text("SELECT set_config('app.current_organization_id', :org_id, false)"), {"org_id": org_b_id})
        await db.execute(text("""
            INSERT INTO users (id, organization_id, email, full_name, password_hash, status, role)
            VALUES (:id, :org_id, :email, :full_name, :password_hash, 'active', 'employee')
        """), {"id": uuid.uuid4().hex, "org_id": org_b_id, "email": f"admin-b-{uuid.uuid4().hex[:8]}@test.com", 
                "full_name": "Org B Admin", "password_hash": "test_hash"})
        await db.commit()
        
        print("Created users for both organizations")
        
        # Create employees
        emp_a_id = uuid.uuid4().hex
        emp_b_id = uuid.uuid4().hex
        
        # Employee for Org A
        await db.execute(text("SELECT set_config('app.current_organization_id', :org_id, false)"), {"org_id": org_a_id})
        await db.execute(text("""
            INSERT INTO employees (id, organization_id, employee_number, first_name, last_name, email, designation, employment_type, status)
            VALUES (:id, :org_id, :emp_num, :first_name, :last_name, :email, :designation, 'full_time', 'active')
        """), {"id": uuid.uuid4().hex, "org_id": org_a_id, "emp_num": f"EMP-{uuid.uuid4().hex[:8]}", 
                "first_name": "Alice", "last_name": "Smith", "email": "alice@org-a.com", "designation": "Engineer"})
        await db.commit()
        
        # Employee for Org B
        await db.execute(text("SELECT set_config('app.current_organization_id', :org_id, false)"), {"org_id": org_b_id})
        await db.execute(text("""
            INSERT INTO employees (id, organization_id, employee_number, first_name, last_name, email, designation, employment_type, status)
            VALUES (:id, :org_id, :emp_num, :first_name, :last_name, :email, :designation, 'full_time', 'active')
        """), {"id": uuid.uuid4().hex, "org_id": org_b_id, "emp_num": f"EMP-{uuid.uuid4().hex[:8]}", 
                "first_name": "Bob", "last_name": "Jones", "email": "bob@org-b.com", "designation": "Designer"})
        await db.commit()
        
        print("Created employees for both organizations")
        
        # Test RLS isolation
        # Test with Org A context
        await db.execute(text("SELECT set_config('app.current_organization_id', :org_id, false)"), {"org_id": org_a_id})
        result = await db.execute(text("SELECT id, organization_id, first_name FROM employees"))
        rows = result.fetchall()
        print(f'\nWith Org A context: {len(rows)} employees')
        for row in rows:
            print(f'  {row.first_name} (org: {row.organization_id})')
        
        # Test with Org B context
        await db.execute(text("SELECT set_config('app.current_organization_id', :org_id, false)"), {"org_id": org_b_id})
        result = await db.execute(text("SELECT id, organization_id, first_name FROM employees"))
        rows = result.fetchall()
        print(f'\nWith Org B context: {len(rows)} employees')
        for row in rows:
            print(f'  {row.first_name} (org: {row.organization_id})')
        
        # Test without context
        await db.execute(text("SELECT set_config('app.current_organization_id', '', false)"))
        result = await db.execute(text("SELECT id, organization_id, first_name FROM employees"))
        rows = result.fetchall()
        print(f'\nWithout context: {len(rows)} employees')
        
        # Cleanup
        await db.execute(text("DELETE FROM employees WHERE organization_id IN (:org_a, :org_b)"), {"org_a": org_a_id, "org_b": org_b_id})
        await db.execute(text("DELETE FROM users WHERE organization_id IN (:org_a, :org_b)"), {"org_a": org_a_id, "org_b": org_b_id})
        await db.execute(text("DELETE FROM organizations WHERE id IN (:org_a, :org_b)"), {"org_a": org_a_id, "org_b": org_b_id})
        await db.commit()
        print("\nCleanup completed!")

asyncio.run(test())
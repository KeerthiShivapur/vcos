from app.db.database import SessionLocal
from app.models.employee import Employee
from app.models.organization import Organization
from app.models.user import User
from sqlalchemy import text
import asyncio
import uuid

async def test():
    async with SessionLocal() as db:
        # Create two organizations
        org_a = Organization(
            id=uuid.uuid4().hex,
            name="Org A Test",
            slug=f"org-a-test-{uuid.uuid4().hex[:8]}",
            industry="Technology",
            country="US",
            timezone="UTC",
            currency="USD",
            status="active",
        )
        org_b = Organization(
            id=uuid.uuid4().hex,
            name="Org B Test",
            slug=f"org-b-test-{uuid.uuid4().hex[:8]}",
            industry="Technology",
            country="US",
            timezone="UTC",
            currency="USD",
            status="active",
        )
        db.add(org_a)
        db.add(org_b)
        await db.flush()
        
        # Create users
        user_a = User(
            id=uuid.uuid4().hex,
            email=f"admin-a-{uuid.uuid4().hex[:8]}@test.com",
            full_name="Org A Admin",
            organization_id=org_a.id,
            status="active",
            password_hash="test_hash",
        )
        user_b = User(
            id=uuid.uuid4().hex,
            email=f"admin-b-{uuid.uuid4().hex[:8]}@test.com",
            full_name="Org B Admin",
            organization_id=org_b.id,
            status="active",
            password_hash="test_hash",
        )
        db.add(user_a)
        db.add(user_b)
        await db.flush()
        
        # Create employees using ORM
        emp_a = Employee(
            id=uuid.uuid4().hex,
            organization_id=org_a.id,
            employee_number=f"EMP-{uuid.uuid4().hex[:8]}",
            first_name="Alice",
            last_name="Smith",
            email="alice@org-a.com",
            designation="Engineer",
            employment_type="full_time",
        )
        emp_b = Employee(
            id=uuid.uuid4().hex,
            organization_id=org_b.id,
            employee_number=f"EMP-{uuid.uuid4().hex[:8]}",
            first_name="Bob",
            last_name="Jones",
            email="bob@org-b.com",
            designation="Designer",
            employment_type="full_time",
        )
        db.add(emp_a)
        db.add(emp_b)
        await db.commit()
        
        print(f"Created emp_a (org_a): {emp_a.id}")
        print(f"Created emp_b (org_b): {emp_b.id}")
        print(f"Org A ID: {org_a.id}")
        print(f"Org B ID: {org_b.id}")
        
        # Test without context
        result = await db.execute(text("SELECT id, organization_id, first_name FROM employees WHERE id IN (:id1, :id2)"), 
                                  {"id1": emp_a.id, "id2": emp_b.id})
        rows = result.fetchall()
        print(f'\nDirect query (no RLS context):')
        for row in rows:
            print(f'  {row.first_name} (org: {row.organization_id})')
        
        # Test with Org A context
        await db.execute(text("SELECT set_config('app.current_organization_id', :org_id, false)"), {"org_id": str(org_a.id)})
        
        # Check the function value
        result = await db.execute(text("SELECT current_organization_id()"))
        func_val = result.scalar()
        print(f'\ncurrent_organization_id(): {func_val}')
        print(f'Org A ID: {org_a.id}')
        print(f'Match: {func_val == org_a.id}')
        
        result = await db.execute(text("SELECT id, organization_id, first_name FROM employees WHERE id IN (:id1, :id2)"), 
                                  {"id1": emp_a.id, "id2": emp_b.id})
        rows = result.fetchall()
        print(f'\nWith Org A context:')
        for row in rows:
            print(f'  {row.first_name} (org: {row.organization_id})')
        
        # Test with Org B context
        await db.execute(text("SELECT set_config('app.current_organization_id', :org_id, false)"), {"org_id": str(org_b.id)})
        
        result = await db.execute(text("SELECT current_organization_id()"))
        func_val = result.scalar()
        print(f'\ncurrent_organization_id(): {func_val}')
        print(f'Org B ID: {org_b.id}')
        print(f'Match: {func_val == org_b.id}')
        
        result = await db.execute(text("SELECT id, organization_id, first_name FROM employees WHERE id IN (:id1, :id2)"), 
                                  {"id1": emp_a.id, "id2": emp_b.id})
        rows = result.fetchall()
        print(f'\nWith Org B context:')
        for row in rows:
            print(f'  {row.first_name} (org: {row.organization_id})')
        
        # Clear context
        await db.execute(text("SELECT set_config('app.current_organization_id', '', false)"))
        
        # Cleanup
        await db.execute(text("DELETE FROM employees WHERE id IN (:id1, :id2)"), {"id1": emp_a.id, "id2": emp_b.id})
        await db.execute(text("DELETE FROM users WHERE organization_id IN (:org_a, :org_b)"), {"org_a": str(org_a.id), "org_b": str(org_b.id)})
        await db.execute(text("DELETE FROM organizations WHERE id IN (:org_a, :org_b)"), {"org_a": str(org_a.id), "org_b": str(org_b.id)})
        await db.commit()

asyncio.run(test())
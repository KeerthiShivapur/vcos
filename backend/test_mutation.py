import asyncio
import uuid
from datetime import datetime
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.organization import Organization
from app.models.user import User
from app.models.employee import Employee
from app.models.role import Role, UserRole
from app.models.company_actions import CompanyAction
from app.intelligence.canonical_mutation import canonical_mutation_boundary
from app.intelligence.canonical_types import MutationType, EpistemicStatus
from app.intelligence.company_context import CallerAccess

async def test():
    engine = create_async_engine('sqlite+aiosqlite:///:memory:', poolclass=StaticPool)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as db:
        # Create org
        org = Organization(id='test-org', name='Test', slug='test', industry='Tech', country='US')
        db.add(org)
        await db.flush()
        
        # Create user
        user = User(id='test-user', organization_id=org.id, email='test@test.com', full_name='Test', password_hash='hash')
        db.add(user)
        await db.flush()
        
        # Create employee
        emp = Employee(organization_id=org.id, user_id=user.id, employee_number='EMP001', first_name='Test', last_name='User', display_name='Test', email='test@test.com', joining_date=datetime.now().date(), status='active', employment_type='full_time')
        db.add(emp)
        await db.flush()
        
        # Create admin role
        from app.models.role import Role, UserRole
        admin_role = Role(id='role-admin', organization_id='test-org', name='Admin', code='admin', description='Admin', is_system=True)
        db.add(admin_role)
        await db.flush()
        
        # Assign admin role
        ur = UserRole(organization_id='test-org', user_id=user.id, role_id=admin_role.id, scope_id=None)
        db.add(ur)
        await db.flush()
        
        # Create employee for caller
        emp2 = Employee(organization_id=org.id, user_id=user.id, employee_number='EMP001', first_name='Test', last_name='User', display_name='Test', email='test@test.com', joining_date=datetime.now().date(), status='active', employment_type='full_time')
        db.add(emp2)
        await db.flush()
        
        caller = CallerAccess(user_id=user.id, organization_id=org.id, employee_id=emp2.id, visible_scope_ids=frozenset([org.id]))
        
        action = CompanyAction(organization_id=org.id, action_type='task', title='Test Action', description='Test', state='proposed', created_by=user.id, fingerprint=f'test-{uuid.uuid4().hex[:16]}')
        
        from app.intelligence.canonical_types import MutationType, EpistemicStatus
        from app.intelligence.canonical_mutation import canonical_mutation_boundary
        
        try:
            result = await canonical_mutation_boundary.mutate(
                db=db,
                caller=caller,
                target_entity_type='CompanyAction',
                mutation_type=MutationType.CREATE,
                entity=action,
                provenance={'test': 'test'},
                epistemic_status=EpistemicStatus.PROPOSED,
            )
            print('Success:', result)
        except Exception as e:
            print(f'ERROR: {type(e).__name__}: {e}')
            import traceback
            traceback.print_exc()

async def test():
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool
    
    engine = create_async_engine('sqlite+aiosqlite:///:memory:', poolclass=StaticPool)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as db:
        # Create org
        from app.models.organization import Organization
        from app.models.user import User
        from app.models.employee import Employee
        from app.models.role import Role, UserRole
        from app.models.company_actions import CompanyAction
        from app.intelligence.canonical_mutation import canonical_mutation_boundary
        from app.intelligence.canonical_types import MutationType, EpistemicStatus
        from app.intelligence.company_context import CallerAccess
        import uuid
        from datetime import datetime
        
        org = Organization(id='test-org', name='Test', slug='test', industry='Tech', country='US')
        db.add(org)
        await db.flush()
        
        user = User(id='test-user', organization_id=org.id, email='test@test.com', full_name='Test', password_hash='hash')
        db.add(user)
        await db.flush()
        
        emp = Employee(organization_id=org.id, user_id=user.id, employee_number='EMP001', first_name='Test', last_name='User', display_name='Test', email='test@test.com', joining_date=datetime.now().date(), status='active', employment_type='full_time')
        db.add(emp)
        await db.flush()
        
        admin_role = Role(id='role-admin', organization_id=org.id, name='Admin', code='admin', description='Admin', is_system=True)
        db.add(admin_role)
        await db.flush()
        
        ur = UserRole(organization_id=org.id, user_id=user.id, role_id=admin_role.id, scope_id=None)
        db.add(ur)
        await db.flush()
        
        emp2 = Employee(organization_id=org.id, user_id=user.id, employee_number='EMP001', first_name='Test', last_name='User', display_name='Test', email='test@test.com', joining_date=datetime.now().date(), status='active', employment_type='full_time')
        db.add(emp2)
        await db.flush()
        
        caller = CallerAccess(user_id=user.id, organization_id=org.id, employee_id=emp.id, visible_scope_ids=frozenset([org.id]))
        
        action = CompanyAction(organization_id=org.id, action_type='task', title='Test Action', description='Test', state='proposed', created_by=user.id, fingerprint=f'test-{uuid.uuid4().hex[:16]}')
        
        from app.intelligence.canonical_types import MutationType, EpistemicStatus
        from app.intelligence.canonical_mutation import canonical_mutation_boundary
        
        try:
            result = await canonical_mutation_boundary.mutate(
                db=db,
                caller=caller,
                target_entity_type='CompanyAction',
                mutation_type=MutationType.CREATE,
                entity=action,
                provenance={'test': 'test'},
                epistemic_status=EpistemicStatus.PROPOSED,
            )
            print('Success:', result)
        except Exception as e:
            print(f'ERROR: {type(e).__name__}: {e}')
            import traceback
            traceback.print_exc()

if __name__ == '__main__':
    asyncio.run(test())
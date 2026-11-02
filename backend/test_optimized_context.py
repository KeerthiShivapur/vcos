import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.pool import NullPool
from sqlalchemy import text
from app.db.database import Base, init_db
from app import models
from app.models.project import Project
from app.models.organization import Organization
from app.models.employee import Employee
from app.models.user import User
from app.intelligence.company_context import build_context
from app.intelligence.company_context_optimized_v2 import build_context_optimized
import uuid
from datetime import datetime

async def test():
    engine = create_async_engine('sqlite+aiosqlite:///test.db', poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    from app.db.database import _create_universal_indexes
    await _create_universal_indexes()
    
    # Create org and data
    async with AsyncSession(engine) as session:
        org_id = 'test-org-' + uuid.uuid4().hex[:8]
        org = Organization(
            id=org_id,
            name='Test Org',
            slug='test-org-' + uuid.uuid4().hex[:8],
            industry='Technology',
            country='US',
            timezone='UTC',
            currency='USD',
        )
        session.add(org)
        
        user_id = uuid.uuid4().hex[:32]
        user = User(
            id=user_id,
            organization_id=org_id,
            email='test@example.com',
            full_name='Test User',
            password_hash='hash',
        )
        session.add(user)
        
        emp = Employee(
            id=uuid.uuid4().hex[:32],
            organization_id=org_id,
            user_id=user_id,
            employee_number='E001',
            first_name='Test',
            last_name='User',
            display_name='Test User',
            email='test@example.com',
            designation='Engineer',
            status='active',
            joining_date=datetime.utcnow(),
        )
        session.add(emp)
        
        for i in range(5):
            p = Project(
                id=uuid.uuid4().hex[:32],
                organization_id=org_id,
                name='Project ' + str(i),
                code='PRJ' + str(i),
                description='Project ' + str(i) + ' description',
                status='active',
                progress=i * 20,
            )
            session.add(p)
        
        await session.commit()
    
    # Test both implementations
    async with AsyncSession(engine) as session:
        # Test original
        result1 = await build_context(
            db=session,
            user=user,
            query='project status',
            organization_id=org_id,
        )
        
        # Test optimized
        result2 = await build_context_optimized(
            db=session,
            user=user,
            query='project status',
            organization_id=org_id,
        )
        
        print('Original evidence count: ' + str(len(result1['evidence'])))
        print('Optimized evidence count: ' + str(len(result2['evidence'])))
        
        # Check evidence types
        types1 = [e['type'] for e in result1['evidence']]
        types2 = [e['type'] for e in result2['evidence']]
        print('Original types: ' + str(types1))
        print('Optimized types: ' + str(types2))

asyncio.run(test())
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool
from sqlalchemy import select, text
from app.db.database import Base
from app import models
from app.models.project import Project
from app.models.organization import Organization
from app.models.user import User
from app.models.employee import Employee
from app.utils.pagination import CursorPaginator, Cursor
import uuid
from datetime import datetime, timezone
import json

async def test():
    engine = create_async_engine('sqlite+aiosqlite:///test.db', poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    # Create org and data
    async with async_session() as session:
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
            joining_date=datetime.now(timezone.utc),
        )
        session.add(emp)
        
        projects = []
        for i in range(15):
            p = Project(
                id=uuid.uuid4().hex[:32],
                organization_id=org_id,
                name=f'Project {i}',
                code=f'PRJ{i}',
                description=f'Project {i} description',
                status='active',
                progress=i * 20,
            )
            session.add(p)
            projects.append(p)
        
        await session.commit()
    
    # Test pagination
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        from app.utils.pagination import CursorPaginator, Cursor
        
        paginator = CursorPaginator(
            model=Project,
            order_by=Project.updated_at.desc(),
            cursor_field=Project.updated_at,
            composite_order_by=[Project.updated_at.desc(), Project.id.desc()],
            composite_cursor_fields=[Project.updated_at, Project.id],
            composite_cursor_decode=lambda x: json.loads(x),
            entity_type='project',
        )
        
        # Debug: print the query
        query = select(Project).where(Project.organization_id == org_id)
        query = query.order_by(Project.updated_at.desc(), Project.id.desc()).limit(6)
        print(f"SQL: {query.compile(compile_kwargs={'literal_binds': True})}")
        result = await session.execute(query)
        items = result.scalars().all()
        print(f'Direct query (limit 6): {len(items)} items')
        
        # Test paginator
        paginator = CursorPaginator(
            model=Project,
            order_by=Project.updated_at.desc(),
            cursor_field=Project.updated_at,
            composite_order_by=[Project.updated_at.desc(), Project.id.desc()],
            composite_cursor_fields=[Project.updated_at, Project.id],
            composite_cursor_decode=lambda x: json.loads(x),
            entity_type='project',
        )
        
        # Debug: check the query being built
        query = select(Project).where(Project.organization_id == org_id)
        query = query.order_by(Project.updated_at.desc(), Project.id.desc()).limit(6)
        print(f"Paginator query limit 6: {len((await session.execute(query)).scalars().all())} items")
        
        # Test paginator with limit
        cursor = None
        page = await paginator.get_page(session, filters=[Project.organization_id == org_id], limit=5)
        print(f'First page: {len(page.items)} items')
        print(f'has_next: {page.has_next}')
        print(f'next_cursor: {page.next_cursor}')
        
        # Check the actual query being executed
        import logging
        logging.basicConfig()
        logging.getLogger('sqlalchemy.engine').setLevel(logging.INFO)
        
        page2 = await paginator.get_page(session, filters=[Project.organization_id == org_id], limit=5)
        print(f'Second call (no cursor): {len(page2.items)} items')

asyncio.run(test())
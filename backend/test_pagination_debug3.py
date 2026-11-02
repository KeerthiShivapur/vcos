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
from datetime import datetime, timezone, timedelta
import json

async def test():
    engine = create_async_engine('sqlite+aiosqlite:///test.db', poolclass=NullPool, echo=True)
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
        base_time = datetime.now(timezone.utc)
        for i in range(15):
            p = Project(
                id=uuid.uuid4().hex[:32],
                organization_id=org_id,
                name=f'Project {i}',
                code=f'PRJ{i}',
                description=f'Project {i} description',
                status='active',
                progress=i * 20,
                updated_at=base_time - timedelta(days=i),
            )
            session.add(p)
            projects.append(p)
        
        await session.commit()
        
        # Print all projects with updated_at
        for i, p in enumerate(projects):
            print(f'Project {i}: id={p.id}, updated_at={p.updated_at}')
    
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
        
        # First page
        cursor = None
        page = await paginator.get_page(session, filters=[Project.organization_id == org_id], limit=5)
        print(f'First page: {len(page.items)} items')
        print(f'has_next: {page.has_next}')
        print(f'next_cursor: {page.next_cursor}')
        
        # Decode cursor
        if page.next_cursor:
            cursor = Cursor.decode(page.next_cursor)
            print(f'Cursor after: {cursor.after}')
            
            # Decode cursor value
            import base64
            encoded, sig = cursor.after.rsplit('.', 1)
            decoded = json.loads(base64.urlsafe_b64decode(encoded).decode())
            print(f'Cursor data: {decoded}')
            
            # Check the cursor's updated_at vs project 4's updated_at
            cursor_updated_at = decoded.get('updated_at')
            print(f'Cursor updated_at: {cursor_updated_at}')
            
            # Check project 4's updated_at
            project4 = projects[4]
            print(f'Project 4 updated_at: {project4.updated_at}')
            print(f'Project 4 id: {project4.id}')
            print(f'Cursor id: {decoded.get("id")}')
            
            # Check if they match
            print(f'Updated_at match: {str(project4.updated_at) == cursor_updated_at}')
            print(f'ID match: {project4.id == decoded.get("id")}')
        
        # Second page
        cursor = Cursor.decode(page.next_cursor) if page.next_cursor else None
        page2 = await paginator.get_page(session, filters=[Project.organization_id == org_id], limit=5, cursor=cursor)
        print(f'Second page: {len(page2.items)} items')
        print(f'has_next: {page2.has_next}')
        
        # Check the actual SQL query
        import logging
        logging.basicConfig()
        logging.getLogger('sqlalchemy.engine').setLevel(logging.INFO)
        
        page3 = await paginator.get_page(session, filters=[Project.organization_id == org_id], limit=5, cursor=cursor)
        print(f'Third call: {len(page3.items)} items')

asyncio.run(test())
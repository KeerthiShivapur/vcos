import asyncio
import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool
from app.services.provisioning_service import provisioning_service, ProvisioningState
from app.intelligence.company_context import resolve_caller_access
from app.models.organization import Organization
from app.models.user import User
from app.models.employee import Employee
from app.models.backup_manifest import BackupManifest, BackupKind, BackupStatus
from app.services.backup_service import BackupService
from app.core.timeutils import utcnow

async def test():
    url = 'postgresql+asyncpg://vcos:vcos@localhost:5432/vcos_test'
    engine = create_async_engine(url, poolclass=NullPool)
    session_factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with session_factory() as session:
        # Provision a company first
        domain = f'test-{uuid.uuid4().hex[:8]}'
        from app.services.provisioning_service import provisioning_service, ProvisioningState
        prov = await provisioning_service.start_provisioning(
            session,
            organization_name='Test Corp',
            domain=domain,
            admin_email=f'admin@{domain}.com',
            admin_name='Admin',
            plan_key='starter',
        )
        result = await provisioning_service.execute_provisioning(session, prov.id)
        org_id = result.organization_id
        print(f'Org created: {org_id}')
        
        # Get admin
        admin_user = await session.execute(select(User).where(User.organization_id == org_id, User.role == 'admin'))
        admin_user = admin_user.scalar_one_or_none()
        admin_emp = await session.execute(select(Employee).where(Employee.user_id == admin_user.id))
        admin_emp = admin_emp.scalar_one_or_none()
        access = await resolve_caller_access(session, organization_id=org_id, user=admin_user)
        
        # Create a test backup
        backup_id = f'bkp-test-{uuid.uuid4().hex[:8]}'
        org_id = result.organization_id
        
        backup = BackupManifest(
            id=f'bkp-test-{uuid.uuid4().hex[:8]}',
            organization_id=org_id,
            backup_kind='full',
            status='completed',
            started_at=utcnow(),
            completed_at=utcnow(),
            retention_days=1,
        )
        session.add(backup)
        await session.flush()
        
        # Test verification
        print('Testing verify_backup...')
        from app.services.backup_service import BackupService
        bs = BackupService()
        verification = await bs.verify_backup(session, backup.id)
        print(f'Verification result: verified={verification.verified}, errors={verification.errors}')

asyncio.run(test())
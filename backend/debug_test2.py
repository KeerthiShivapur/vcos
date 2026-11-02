import asyncio
import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool
from app.models.organization import Organization
from app.models.user import User
from app.models.employee import Employee
from app.core.timeutils import utcnow
from app.services.provisioning_service import provisioning_service, ProvisioningState
from app.services.external_identity_service import external_identity_service

async def test():
    url = 'postgresql+asyncpg://vcos:vcos@localhost:5432/vcos_test'
    engine = create_async_engine(url, poolclass=NullPool)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with session_factory() as session:
        domain = f'test-{uuid.uuid4().hex[:8]}'
        prov = await provisioning_service.start_provisioning(
            session, organization_name='Test', domain=domain,
            admin_email=f'admin@{domain}.com', admin_name='Admin', plan_key='starter'
        )
        result = await provisioning_service.execute_provisioning(session, prov.id)
        org_id = result.organization_id
        
        from app.models.canonical_integration import ConnectorInstance as CI, Connector
        connector = await session.execute(select(Connector).where(Connector.provider == 'google'))
        connector = connector.scalar_one_or_none()
        if not connector:
            connector = Connector(
                kind='productivity', provider='google', display_name='Google',
                description='Test', enabled=True,
            )
            session.add(connector)
            await session.flush()
        
        instance = CI(organization_id=org_id, connector_id=connector.id, name='Test',
            config={}, credentials={}, state='connected', auth_type='oauth2')
        session.add(instance)
        await session.flush()
        
        admin_user = await session.execute(select(User).where(User.organization_id == org_id, User.role == 'admin'))
        admin_user = admin_user.scalar_one_or_none()
        admin_emp = await session.execute(select(Employee).where(Employee.user_id == admin_user.id))
        admin_emp = admin_emp.scalar_one_or_none()
        
        mapping = await external_identity_service.resolve_identity(
            db=session, organization_id=org_id, connector_instance_id=instance.id,
            external_id='fake_id', external_email='fake@google.com', external_display_name='Fake',
        )
        print(f'Mapping state: {mapping.mapping_state}')
        print(f'Mapping vcos_entity_id: "{mapping.vcos_entity_id}"')
        
        try:
            await external_identity_service.resolve_mapping(
                db=session, mapping_id=mapping.id, organization_id=org_id,
                resolved_by=admin_emp.id, vcos_entity_id=admin_emp.id, resolution_method='manual',
            )
            print('No exception raised!')
        except ValueError as e:
            print(f'ValueError raised: {e}')

asyncio.run(test())
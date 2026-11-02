import asyncio
import uuid
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

from app.models.organization import Organization
from app.models.release import ReleaseRecord, ReleaseFailureInjection
from app.services.release_failure_recovery import ReleaseFailureRecoveryService


async def test():
    engine = create_async_engine(
        'postgresql+asyncpg://vcos:vcos@localhost:5432/vcos_test',
        poolclass=NullPool,
        echo=False,
    )
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with session_factory() as session:
        org = Organization(name='Test', slug=f'test-slug-{uuid.uuid4().hex[:8]}', status='active')
        session.add(org)
        await session.flush()
        await session.commit()
        
        service = ReleaseFailureRecoveryService()
        release = await service.create_release_record(
            db=session,
            organization_id=org.id,
            version='1.0.0',
            initiated_by='test-user',
        )
        
        service2 = ReleaseFailureRecoveryService()
        injection = await service2.inject_preflight_failure(
            db=session,
            release_id=release.id,
            error_message='Test',
        )
        
        print('Type of injection:', type(injection))
        print('Has error_message:', hasattr(injection, 'error_message'))
        if hasattr(injection, 'error_message'):
            print('error_message:', injection.error_message)
    
    await engine.dispose()


asyncio.run(test())
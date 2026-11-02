import os
os.environ['VCOS_TEST_MODE'] = '1'

print(f'VCOS_TEST_MODE = {os.environ.get("VCOS_TEST_MODE")}')

from app.validation.capability_contract import CapabilityDetector, EnvironmentCapability
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool
import asyncio

async def test():
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import NullPool
    
    url = 'postgresql+asyncpg://vcos:vcos@localhost:5432/vcos_test'
    engine = create_async_engine(url, poolclass=NullPool)
    session_factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with session_factory() as session:
        detector = CapabilityDetector(db=session)
        # Test a few capabilities
        for cap in [EnvironmentCapability.CANONICAL_OBSERVATIONS, EnvironmentCapability.COMPANY_TIMELINE_EVENT, EnvironmentCapability.FUTURE_SIMULATOR_CALIBRATION, EnvironmentCapability.AUTONOMY_POLICIES]:
            result = await detector.detect(cap)
            print(f'{cap.name}: {cap} = {result}')

    await engine.dispose()

if __name__ == '__main__':
    import asyncio
    asyncio.run(test())
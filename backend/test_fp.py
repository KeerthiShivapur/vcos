import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import text
from app.services.canonical_fingerprint import canonical_fingerprint_service, CANONICAL_COMPONENTS
from app.core.config import get_settings

async def test_fingerprint():
    engine = create_async_engine('postgresql+asyncpg://postgres:postgres@localhost:5432/vcos_test', poolclass=None)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    settings = get_settings()
    
    async with session_factory() as db:
        # Test with a specific organization
        org_id = "test-org-123"
        
        import time
        start = time.time()
        
        # Compute tenant fingerprint
        fp = await canonical_fingerprint_service.compute_tenant_fingerprint(
            db=db,
            organization_id=org_id,
        )
        
        elapsed = time.time() - start
        print(f"Fingerprint computed in {elapsed:.2f}s")
        print(f"Status: {fp.status}")
        print(f"Aggregate: {fp.aggregate_fingerprint[:16]}...")
        print(f"Components: {len(fp.components)}")
        for c in fp.components:
            print(f"  {c.component_name}: {c.entity_count} entities, {c.fingerprint[:16]}...")
    
    await engine.dispose()

asyncio.run(test_fingerprint())
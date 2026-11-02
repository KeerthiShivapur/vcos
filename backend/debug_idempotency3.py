#!/usr/bin/env python
"""Debug idempotency check with explicit commits."""

import asyncio
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

os.environ["DATABASE_URL"] = "postgresql+asyncpg://postgres:postgres@localhost:5432/vcos_test"
os.environ["VCOS_TEST_MODE"] = "0"
os.environ["REDIS_ENABLED"] = "false"
os.environ["RATE_LIMIT_ENABLED"] = "false"
os.environ["EMAIL_TRANSPORT"] = "console"
os.environ["AI_PROVIDER"] = "none"
os.environ["SECRET_KEY"] = "test-secret-key-not-for-production"
os.environ["APP_ENV"] = "test"

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select, text

from app.services.provisioning_service import provisioning_service
from app.models.finance import Provisioning


engine = create_async_engine(
    "postgresql+asyncpg://postgres:postgres@localhost:5432/vcos_test",
    echo=True,
)

async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def test_idempotency():
    print("Testing idempotency check with explicit commits...")
    
    idempotency_key = "test-idem-key-123"
    domain = f"test-{uuid.uuid4().hex[:8]}.com"
    
    print(f"Idempotency key: {idempotency_key}")
    print(f"Domain: {domain}")
    
    # First request - explicit commit
    print("\n=== First request ===")
    async with async_session() as db:
        prov1 = await provisioning_service.start_provisioning(
            db,
            organization_name="Idempotency Test",
            domain=domain,
            admin_email="admin@test.com",
            admin_name="Admin",
            plan_key="starter",
            idempotency_key="test-idem-key-123",
        )
        print(f"First request: provisioning_id={prov1.id}")
        print(f"Provisioning metadata: {prov1.metadata_json}")
        
        await db.commit()
        print("First request committed (explicit commit)")
    
    # Longer delay and new session
    await asyncio.sleep(0.5)
    
    # Check if data is visible in new session
    print("\n=== Checking visibility in new session ===")
    async with async_session() as db:
        from app.models.finance import Provisioning
        from sqlalchemy import select
        
        # Check if provisioning exists with idempotency key
        result = await db.execute(
            select(Provisioning).where(text("(metadata_json::jsonb ->> 'idempotency_key') = :key")).params(key="test-idem-key-123")
        )
        existing = result.scalar_one_or_none()
        if existing:
            print(f"Found existing provisioning: {existing.id}")
            print(f"Metadata: {existing.metadata_json}")
        else:
            print("No existing provisioning found with idempotency_key")
    
    # Second request (new session)
    await asyncio.sleep(0.5)
    
    print("\n=== Second request (different domain, same idempotency key) ===")
    async with async_session() as db:
        try:
            prov2 = await provisioning_service.start_provisioning(
                db,
                organization_name="Idempotency Test 2",
                domain="different-domain.com",
                admin_email="admin2@test.com",
                admin_name="Admin 2",
                plan_key="starter",
                idempotency_key="test-idem-key-123",
            )
            print(f"Second request succeeded (unexpected): provisioning_id={prov2.id}")
        except ValueError as e:
            print(f"Second request failed as expected: {e}")
        
        await db.commit()
    
    print("\nTest completed")


if __name__ == "__main__":
    asyncio.run(test_idempotency())
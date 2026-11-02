#!/usr/bin/env python
"""Debug idempotency with longer delays and verification."""

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
from app.models.organization import Organization


engine = create_async_engine(
    "postgresql+asyncpg://postgres:postgres@localhost:5432/vcos_test",
    echo=False,
)

async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def test_idempotency_sequential():
    print("Testing idempotency with longer delays...")
    
    idempotency_key = f"test-idem-seq-{uuid.uuid4().hex[:8]}"
    domain = f"seq-test-{uuid.uuid4().hex[:8]}.com"
    
    print(f"Idempotency key: {idempotency_key}")
    print(f"Domain: {domain}")
    
    # First request
    print("\n=== First request ===")
    async with async_session() as db:
        prov1 = await provisioning_service.start_provisioning(
            db,
            organization_name="Sequential Idempotency Test",
            domain=domain,
            admin_email="admin@seq-test.com",
            admin_name="Admin",
            plan_key="starter",
            idempotency_key="test-seq-key-123",
        )
        print(f"First request: provisioning_id={prov1.id}")
        print(f"Provisioning metadata: {prov1.metadata_json}")
        
        await db.commit()
        print("First request committed")
    
    # Verify data is visible in new session with longer delay
    print("\n=== Verifying visibility after 1 second ===")
    await asyncio.sleep(1.0)
    
    async with async_session() as db:
        from sqlalchemy import select, text
        from app.models.finance import Provisioning
        
        result = await db.execute(
            select(Provisioning).where(
                text("(metadata_json::jsonb ->> 'idempotency_key') = :key")
            ).params(key="test-seq-key-123")
        )
        existing = result.scalar_one_or_none()
        if existing:
            print(f"Found existing provisioning: {existing.id}")
            print(f"Metadata: {existing.metadata_json}")
        else:
            print("No existing provisioning found with idempotency_key")
    
    # Second request (new session) - same idempotency key, same payload
    print("\n=== Second request (same payload) ===")
    async with async_session() as db:
        prov2 = await provisioning_service.start_provisioning(
            db,
            organization_name="Idempotency Test",
            domain=domain,
            admin_email="admin@test.com",
            admin_name="Admin",
            plan_key="starter",
            idempotency_key="test-seq-key-123",
        )
        print(f"Second request: provisioning_id={prov2.id}")
        
        if prov2.id == prov1_id:
            print("PASS: Same provisioning returned for same idempotency key")
        else:
            print(f"FAIL: Different provisioning! Expected {prov1_id}, got {prov2.id}")
        
        await db.commit()
    
    print("\nTest completed")


async def main():
    global prov1_id
    prov1_id = None
    
    idempotency_key = "test-seq-key-123"
    domain = f"seq-test-{uuid.uuid4().hex[:8]}.com"
    
    print(f"Idempotency key: {idempotency_key}")
    print(f"Domain: {domain}")
    
    # First request
    print("\n=== First request ===")
    async with async_session() as db:
        prov1 = await provisioning_service.start_provisioning(
            db,
            organization_name="Sequential Idempotency Test",
            domain=domain,
            admin_email="admin@test.com",
            admin_name="Admin",
            plan_key="starter",
            idempotency_key="test-seq-key-123",
        )
        prov1_id = prov1.id
        print(f"First request: provisioning_id={prov1.id}")
        print(f"Provisioning metadata: {prov1.metadata_json}")
        
        await db.commit()
        print("First request committed")
    
    # Verify data is visible in new session with longer delay
    print("\n=== Verifying visibility after 1 second ===")
    await asyncio.sleep(1.0)
    
    async with async_session() as db:
        from sqlalchemy import select, text
        from app.models.finance import Provisioning
        
        result = await db.execute(
            select(Provisioning).where(
                text("(metadata_json::jsonb ->> 'idempotency_key') = :key")
            ).params(key="test-seq-key-123")
        )
        existing = result.scalar_one_or_none()
        if existing:
            print(f"Found existing provisioning: {existing.id}")
            print(f"Metadata: {existing.metadata_json}")
        else:
            print("No existing provisioning found with idempotency_key")
    
    # Second request (new session) - same idempotency key, same payload
    print("\n=== Second request (same payload) ===")
    async with async_session() as db:
        prov2 = await provisioning_service.start_provisioning(
            db,
            organization_name="Sequential Idempotency Test",
            domain=domain,
            admin_email="admin@test.com",
            admin_name="Admin",
            plan_key="starter",
            idempotency_key="test-seq-key-123",
        )
        print(f"Second request: provisioning_id={prov2.id}")
        
        if prov2.id == prov1_id:
            print("PASS: Same provisioning returned for same idempotency key")
        else:
            print(f"FAIL: Different provisioning! Expected {prov1_id}, got {prov2.id}")
        
        await db.commit()
    
    print("\nTest completed")


if __name__ == "__main__":
    asyncio.run(main())
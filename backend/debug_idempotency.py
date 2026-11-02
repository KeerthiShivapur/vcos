#!/usr/bin/env python
"""Debug idempotency check."""

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


engine = create_async_engine(
    "postgresql+asyncpg://postgres:postgres@localhost:5432/vcos_test",
    echo=False,
)

async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def test_idempotency():
    print("Testing idempotency check...")
    
    async with async_session() as db:
        # First request
        idempotency_key = f"test-idem-{uuid.uuid4().hex[:8]}"
        domain = f"test-{uuid.uuid4().hex[:8]}.com"
        
        print(f"Idempotency key: {idempotency_key}")
        print(f"Domain: {domain}")
        
        prov1 = await provisioning_service.start_provisioning(
            db,
            organization_name="Idempotency Test",
            domain=domain,
            admin_email="admin@test.com",
            admin_name="Admin",
            plan_key="starter",
            idempotency_key=idempotency_key,
        )
        print(f"First request: provisioning_id={prov1.id}")
        
        await db.commit()
        print("First request committed")
    
    # Second request (new session)
    await asyncio.sleep(0.1)
    
    async with async_session() as db:
        prov2 = await provisioning_service.start_provisioning(
            db,
            organization_name="Idempotency Test",
            domain=f"idempotency-test-{uuid.uuid4().hex[:8]}.com",  # Different domain
            admin_email="admin@test.com",
            admin_name="Admin",
            plan_key="starter",
            idempotency_key=idempotency_key,
        )
        print(f"Second request: provisioning_id={prov2.id}")
        
        await db.commit()
    
    # Check if they're the same
    print("Test completed")


if __name__ == "__main__":
    asyncio.run(test_idempotency())
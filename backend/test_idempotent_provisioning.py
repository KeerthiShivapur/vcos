#!/usr/bin/env python
"""Test idempotent provisioning with exact-once semantics."""

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
from sqlalchemy import select

from app.services.provisioning_service import provisioning_service
from app.models.organization import Organization


async def test_idempotent_provisioning():
    """Test idempotent provisioning with exact-once semantics."""
    print("=" * 80)
    print("IDEMPOTENT PROVISIONING TEST")
    print("=" * 80)
    
    engine = create_async_engine(
        "postgresql+asyncpg://postgres:postgres@localhost:5432/vcos_test",
        echo=False,
    )
    
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as db:
        # Test 1: Same idempotency key, same payload - should return same provisioning
        print("\nTest 1: Same idempotency key, same payload")
        print("-" * 80)
        
        idempotency_key = f"idem-{uuid.uuid4().hex[:8]}"
        domain = f"idem-test-{uuid.uuid4().hex[:8]}.com"
        
        # First request
        prov1 = await provisioning_service.start_provisioning(
            db,
            organization_name="Idempotent Test Corp",
            domain=domain,
            admin_email="admin@idem-test.com",
            admin_name="Admin User",
            plan_key="starter",
            idempotency_key=idempotency_key,
        )
        print(f"First request: provisioning_id={prov1.id}, org_id={prov1.organization_id}")
        
        # Second request with same key and payload
        prov2 = await provisioning_service.start_provisioning(
            db,
            organization_name="Idempotent Test Corp",
            domain=domain,
            admin_email="admin@idem-test.com",
            admin_name="Admin User",
            plan_key="starter",
            idempotency_key=idempotency_key,
        )
        print(f"Second request: provisioning_id={prov2.id}, org_id={prov2.organization_id}")
        
        assert prov1.id == prov2.id, "Same idempotency key should return same provisioning"
        assert prov1.organization_id == prov2.organization_id, "Same organization should be returned"
        print("PASS: Same idempotency key with same payload returns same provisioning")
        
        # Test 2: Same idempotency key, different payload - should raise conflict
        print("\nTest 2: Same idempotency key, different payload")
        print("-" * 80)
        
        idempotency_key2 = f"idem-{uuid.uuid4().hex[:8]}"
        domain2 = f"idem-test-{uuid.uuid4().hex[:8]}.com"
        
        # First request
        prov3 = await provisioning_service.start_provisioning(
            db,
            organization_name="Conflict Test Corp",
            domain=domain2,
            admin_email="admin@conflict-test.com",
            admin_name="Admin User",
            plan_key="starter",
            idempotency_key=idempotency_key2,
        )
        print(f"First request: provisioning_id={prov3.id}, org_id={prov3.organization_id}")
        
        # Second request with same key but different payload
        try:
            prov4 = await provisioning_service.start_provisioning(
                db,
                organization_name="Different Corp",  # Different name
                domain=domain2,
                admin_email="different@conflict-test.com",  # Different email
                admin_name="Different Admin",  # Different name
                plan_key="professional",  # Different plan
                idempotency_key=idempotency_key2,
            )
            print("FAIL: Should have raised conflict error")
            return False
        except ValueError as e:
            if "Idempotency key conflict" in str(e):
                print("PASS: Conflict detected - " + str(e))
            else:
                print("FAIL: Wrong error - " + str(e))
                return False
        
        # Test 3: No idempotency key - should create new provisioning each time (different domains)
        print("\nTest 3: No idempotency key - creates new provisioning each time")
        print("-" * 80)
        
        domain3 = f"no-idem-{uuid.uuid4().hex[:8]}.com"
        prov5 = await provisioning_service.start_provisioning(
            db,
            organization_name="No Idempotency Corp 1",
            domain=domain3,
            admin_email="admin1@no-idem.com",
            admin_name="Admin User 1",
            plan_key="starter",
        )
        print(f"First request (no key): provisioning_id={prov5.id}, org_id={prov5.organization_id}")
        
        domain4 = f"no-idem-{uuid.uuid4().hex[:8]}.com"
        prov6 = await provisioning_service.start_provisioning(
            db,
            organization_name="No Idempotency Corp 2",
            domain=domain4,
            admin_email="admin2@no-idem.com",
            admin_name="Admin User 2",
            plan_key="starter",
        )
        print(f"Second request (no key): provisioning_id={prov6.id}, org_id={prov6.organization_id}")
        
        assert prov5.id != prov6.id, "Without idempotency key, should create new provisioning"
        assert prov5.organization_id != prov6.organization_id, "Should create different organizations"
        print("PASS: Without idempotency key, creates new provisioning each time")
        
        print("\n" + "=" * 80)
        print("ALL IDEMPOTENCY TESTS PASSED")
        print("=" * 80)
        return True
    
    await engine.dispose()
    return False


if __name__ == "__main__":
    result = asyncio.run(test_idempotent_provisioning())
    sys.exit(0 if result else 1)
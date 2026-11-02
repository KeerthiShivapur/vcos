import os
os.environ['TEST_DATABASE_URL'] = 'postgresql+asyncpg://postgres:postgres@localhost:5432/vcos_test'
os.environ['PATH'] += ';C:\\Program Files\\PostgreSQL\\18\\bin'

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy import create_engine, text
import asyncio
import time
import uuid
import sys

async def test():
    print("Creating sync engine...")
    sync_url = "postgresql+psycopg2://postgres:postgres@localhost:5432/vcos_test"
    sync_engine = create_engine(
        sync_url,
        pool_size=1,
        max_overflow=0,
        pool_pre_ping=True,
        connect_args={"options": "-c search_path=public"},
        echo=False,
        future=True,
    )
    sync_session_factory = sessionmaker(
        sync_engine,
        class_=Session,
        expire_on_commit=False,
    )
    print("Sync engine created")
    
    with sync_session_factory() as sync_db:
        org = Organization(
            id=uuid.uuid4().hex[:32],
            name="Scale Test startup (5 employees)",
            slug=f"scale-startup-{uuid.uuid4().hex[:8]}",
            industry="Technology",
            country="US",
            timezone="UTC",
            currency="USD",
            language="en",
            status="active",
        )
        sync_db.add(org)
        sync_db.flush()
        org_id = org.id
        print(f"Created org: {org_id}")
        
        from tests.scale.generators import SyncScaleGenerator, UniversalScaleProfile, UNIVERSAL_SCALE_PROFILES
        
        profile = UNIVERSAL_SCALE_PROFILES.get("startup")
        if not profile:
            profile = UniversalScaleProfile(name="startup", employee_count=5)
        
        print(f"Profile: {profile.name}, employees: {profile.employee_count}")
        
        generator = SyncScaleGenerator(sync_db, org_id, profile)
        
        print("Generating...")
        start = time.perf_counter()
        counts = generator.generate_all()
        generation_time = time.perf_counter() - start
        
        total_rows = sum(counts.values())
        throughput = total_rows / generation_time if generation_time > 0 else 0
        
        print(f"Generation time: {generation_time:.2f}s")
        print(f"Total rows: {total_rows}")
        print(f"Throughput: {throughput:.2f} rows/sec")
        print(f"Counts: {counts}")
    
    print("Done")

import asyncio
import time
import uuid
from app.models.organization import Organization
asyncio.run(test())
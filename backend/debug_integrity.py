import asyncio
import os
import uuid
import hashlib
from datetime import datetime, timezone, timedelta

os.environ['TEST_DATABASE_URL'] = 'postgresql+asyncpg://vcos:vcos@localhost:5432/vcos_test'
os.environ['VCOS_TEST_MODE'] = '1'

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.pool import NullPool
from sqlalchemy import text

from app.models.organization import Organization
from app.models.backup_manifest import BackupManifest, BackupStatus, BackupKind
from app.models.governance import ApprovalPolicy
from app.models.observability import HealthDimension
from app.services.canonical_reality_integrity_service import canonical_reality_integrity_service


async def test():
    engine = create_async_engine(
        "postgresql+asyncpg://vcos:vcos@localhost:5432/vcos_test",
        poolclass=NullPool,
        connect_args={"server_settings": {"search_path": "public"}},
        echo=False,
        future=True,
    )
    
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with session_factory() as session:
        org = Organization(
            name='Test Org',
            slug=f'test-org-debug-{uuid.uuid4().hex[:8]}',
            status='active',
        )
        session.add(org)
        await session.flush()
        
        backup = BackupManifest(
            id=f'bkp-test-{uuid.uuid4().hex[:8]}',
            organization_id=org.id,
            backup_kind=BackupKind.PRE_DEPLOYMENT,
            status=BackupStatus.VERIFIED,
            started_at=datetime.now(timezone.utc) - timedelta(hours=1),
            completed_at=datetime.now(timezone.utc) - timedelta(minutes=30),
            backup_size_bytes=1024 * 1024 * 100,
            checksum_sha256='a' * 64,
        )
        session.add(backup)
        await session.flush()
        
        policy = ApprovalPolicy(
            organization_id=org.id,
            name='Test Policy',
            approval_type='decision',
            required_permission='decision:create',
        )
        session.add(policy)
        
        fingerprint = hashlib.sha256(f'api_latency|{org.id}|company|'.encode()).hexdigest()[:64]
        health = HealthDimension(
            organization_id=org.id,
            dimension='api_latency',
            scope_type='company',
            scope_id=None,
            status='healthy',
            current_value=50.0,
            target_value=100.0,
            recorded_at=datetime.now(timezone.utc),
            fingerprint=fingerprint,
        )
        session.add(health)
        await session.commit()
        
        # Run canonical integrity check directly
        findings = await canonical_reality_integrity_service.run_integrity_scan(
            db=session,
            organization_id=org.id,
            checks=['structural', 'tenant', 'temporal', 'provenance', 'epistemic', 'operating_chain'],
            limit=10,
        )
        
        print(f'Total findings: {len(findings)}')
        for f in findings:
            print(f'  {f.finding_type.value}: {f.severity.value} - {f.title}')
        
        critical = [f for f in findings if f.severity.value == 'critical']
        high = [f for f in findings if f.severity.value == 'high']
        print(f'Critical: {len(critical)}, High: {len(high)}')
    
    await engine.dispose()


asyncio.run(test())
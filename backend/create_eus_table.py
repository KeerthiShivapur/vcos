import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import MetaData, Table, Column, String, DateTime, JSON, Integer, ForeignKey, Index, UniqueConstraint, text
from datetime import datetime, timezone

async def create_table():
    engine = create_async_engine('postgresql+asyncpg://postgres:postgres@localhost:5432/vcos_test', poolclass=None)
    
    metadata = MetaData()
    
    external_unknown_states = Table(
        'external_unknown_states', metadata,
        Column('id', String(32), primary_key=True),
        Column('organization_id', String(32), ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False, index=True),
        Column('operation_id', String(32), ForeignKey('external_operations.id', ondelete='CASCADE'), nullable=False, index=True),
        Column('external_system', String(60), nullable=False, index=True),
        Column('external_operation_id', String(255), nullable=False, index=True),
        Column('external_operation_type', String(60)),
        Column('request_payload_json', JSON),
        Column('request_fingerprint', String(160), nullable=False),
        Column('state', String(20), default='unknown', nullable=False, index=True),
        Column('requested_at', DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)),
        Column('last_checked_at', DateTime(timezone=True)),
        Column('timeout_at', DateTime(timezone=True)),
        Column('reconciliation_id', String(32)),
        Column('reconciliation_state', String(20)),
        Column('external_state_json', JSON),
        Column('reconciliation_method', String(30)),
        Column('reconciliation_result_json', JSON),
        Column('evidence_fingerprints', JSON, default=list),
        Column('evidence_details_json', JSON),
        Column('actor_id', String(64)),
        Column('fingerprint', String(160), nullable=False),
        Column('version', Integer, default=1, nullable=False),
        Column('created_at', DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)),
        Column('updated_at', DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc)),
        Index('ix_eus_org_state', 'organization_id', 'state'),
        Index('ix_eus_org_operation', 'organization_id', 'operation_id'),
        Index('ix_eus_external', 'external_system', 'external_operation_id'),
        UniqueConstraint('organization_id', 'fingerprint', name='uq_eus_fp_exact_once'),
    )
    
    async with engine.begin() as conn:
        await conn.run_sync(metadata.create_all)
    
    await engine.dispose()
    print('Table created')

asyncio.run(create_table())
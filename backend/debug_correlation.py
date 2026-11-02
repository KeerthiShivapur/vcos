import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import select
from app.models.observability import CorrelationContext
from app.models.organization import Organization
from app.services.observability_service import observability_service
from app.core.timeutils import utcnow
from app.services.observability_service import CorrelationChainStep
from app.db.database import Base
import uuid

async def test():
    engine = create_async_engine('sqlite+aiosqlite:///:memory:', echo=False)
    async with engine.begin() as conn:
        from app.db.database import Base
        await conn.run_sync(Base.metadata.create_all)
    
    async_session = async_sessionmaker(engine, expire_on_commit=False)
    async with async_session() as db:
        org = Organization(id='org-1', name='Test', slug='test', industry='Software', country='US', timezone='UTC', currency='USD')
        db.add(org)
        await db.flush()
        
        trace_id = 'trace-test'
        for i in range(3):
            from app.services.observability_service import observability_service
            from app.services.observability_service import CorrelationChainStep
            from app.core.timeutils import utcnow
            
            ctx = await observability_service.create_correlation_context(
                db=db,
                organization_id='org-1',
                correlation_type='request_flow',
                correlation_id=f'corr-{i}',
                trace_id='trace-test',
            )
            
            step = CorrelationChainStep(
                step_number=1,
                observation_type='request',
                source='api',
                operation_id=f'op-{i}',
                actor_id='user-123',
                observed_at=utcnow(),
                outcome='success',
            )
            await observability_service.add_correlation_step(
                db=db,
                correlation_context=ctx,
                step=step,
            )
            print(f'Created ctx {i}: id={ctx.id}, corr_id={ctx.correlation_id}, trace_id={ctx.trace_id}, steps={ctx.chain_json}')
        
        # Check what's in the database
        result = await db.execute(
            select(CorrelationContext).where(
                CorrelationContext.organization_id == 'org-1',
                CorrelationContext.trace_id == trace_id,
            )
        )
        contexts = result.scalars().all()
        print(f'Found {len(contexts)} contexts with trace_id=trace-test')
        for ctx in contexts:
            print(f'  ctx.id={ctx.id}, corr_id={ctx.correlation_id}, trace_id={ctx.trace_id}, steps={ctx.chain_json}')
        
        # Now test reconstruct
        from app.services.observability_service import observability_service
        chain = await observability_service.reconstruct_correlation_chain(
            db=db,
            organization_id='org-1',
            trace_id=trace_id,
        )
        print(f'Chain length: {len(chain)}')
        for step in chain:
            print(f'  step: corr_id={step.get("correlation_id")}, obs_type={step.get("observation_type")}')

asyncio.run(test())
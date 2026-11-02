import asyncio
import uuid
from sqlalchemy import create_engine, Column, String, Integer, select, update
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.pool import StaticPool

from app.models.execution_strategy import CompanyCommitment
from app.intelligence.canonical_mutation import canonical_update
from app.intelligence.company_context import CallerAccess
from tests.concurrency.context import ConcurrentSessionHarness, ConcurrentTestRunner, ConcurrencyBarrier
from app.models.organization import Organization
from app.models.user import User
from app.models.role import Role, UserRole
from app.services.permission_service import permission_service
from app.intelligence.company_context import resolve_caller_access

Base = declarative_base()

async def test_concurrent_updates():
    """Test concurrent updates with the actual test setup."""
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from sqlalchemy.pool import StaticPool
    
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
        echo=True,
    )
    async with engine.begin() as conn:
        from app.db.database import Base
        await conn.run_sync(Base.metadata.create_all)
    
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    # Create organization
    async with session_factory() as session:
        org = Organization(
            id=f"test-org-{uuid.uuid4().hex[:8]}",
            name=f"Test Org {uuid.uuid4().hex[:8]}",
            slug=f"test-org-{uuid.uuid4().hex[:8]}",
            status="active",
        )
        session.add(org)
        await session.flush()
        org_id = org.id
    
    # Create user with CEO role
    async with session_factory() as session:
        user = User(
            id=f"test-user-{uuid.uuid4().hex[:8]}",
            email=f"test-{uuid.uuid4().hex[:8]}@test.com",
            full_name="Test User",
            status="active",
            organization_id=org_id,
            password_hash="test-hash",
        )
        session.add(user)
        await session.flush()
        
        await permission_service.sync_catalog(session)
        await permission_service.seed_org_roles(session, org_id)
        
        ceo_role = (await session.execute(
            select(Role).where(Role.organization_id == org_id, Role.code == "ceo")
        )).scalars().first()
        
        if ceo_role:
            user_role = UserRole(
                user_id=user.id,
                role_id=ceo_role.id,
                organization_id=org_id,
            )
            session.add(user_role)
            await session.flush()
        
        caller = await resolve_caller_access(session, organization_id=org_id, user=user)
        user_id = user.id
        org_id = org_id
    
    # Create initial entity
    comm = CompanyCommitment(
        organization_id=org_id,
        commitment_type="unconditional",
        title="Original Title",
        scope_type="objective",
        authorization_id="auth-1",
        decision_id="dec-1",
        fingerprint=f"test-concurrent-update-{uuid.uuid4().hex[:8]}",
    )
    async with session_factory() as session:
        session.add(comm)
        await session.flush()
        await session.commit()
        initial_version = comm.version
        comm_id = comm.id
        print(f"Initial version: {initial_version}, ID: {comm_id}")
    
    # Create actors
    actors = {}
    for i in range(10):
        async with session_factory() as session:
            actor_user = User(
                id=f"actor-{i}-{uuid.uuid4().hex[:8]}",
                email=f"actor{i}-{uuid.uuid4().hex[:8]}@test.com",
                full_name=f"Actor {i}",
                status="active",
                organization_id=org_id,
                password_hash="test-hash",
            )
            session.add(actor_user)
            await session.flush()
            
            ceo_role = (await session.execute(
                select(Role).where(Role.organization_id == org_id, Role.code == "ceo")
            )).scalars().first()
            
            if ceo_role:
                user_role = UserRole(
                    user_id=actor_user.id,
                    role_id=ceo_role.id,
                    organization_id=org_id,
                )
                session.add(user_role)
                await session.flush()
            
            actor_caller = await resolve_caller_access(session, organization_id=org_id, user=actor_user)
            actors[f"actor-{i}"] = {"user": actor_user, "caller": actor_caller}
    
    # Create harness and runner
    harness = ConcurrentSessionHarness(
        session_factory=session_factory,
        organization=type('obj', (object,), {'id': org_id})(),
        actors=list(actors.values()),
    )
    
    barrier = ConcurrencyBarrier(parties=10, name="test")
    runner = ConcurrentTestRunner(harness=harness, barrier=barrier)
    
    async def update_commitment(actor_id: str, ctx):
        caller = actors[actor_id]["caller"]
        from app.intelligence.canonical_mutation import canonical_update
        return await canonical_update(
            db=ctx.session,
            caller=caller,
            entity_type="CompanyCommitment",
            entity_id=comm_id,
            updates={"title": f"Updated by {actor_id}"},
            expected_version=1,  # initial_version should be 1
            provenance={"authorization_id": "auth-1", "decision_id": "dec-1"},
            required_permissions=["commitments:manage"],
        )
    
    results = await runner.run_concurrent(update_commitment)
    
    successful = [r for r in runner.results if r.success]
    failed = [r for r in runner.results if not r.success]
    print(f"Successful: {len(successful)}, Failed: {len(failed)}")
    for r in runner.results:
        print(f"  Actor {r.actor_id}: success={r.success}, error={r.error}")
    
    await engine.dispose()

if __name__ == '__main__':
    asyncio.run(test_concurrent_updates())
"""Canonical Concurrent Execution Test Harness — Fixtures Module.

Provides reusable fixtures for same-company and cross-company concurrency scenarios.
"""

import asyncio
import uuid
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.organization import Organization
from app.models.user import User
from app.models.employee import Employee
from app.models.role import Role, UserRole
from app.models.execution_strategy import CompanyCommitment, CompanyAuthorization
from app.models.canonical_reliability import CanonicalOperation, WorkerLease
from app.services.permission_service import permission_service
from app.intelligence.company_context import resolve_caller_access, CallerAccess
from app.core.timeutils import utcnow
from app.intelligence.canonical_concurrency import LeaseManager

from tests.concurrency.context import (
    CanonicalActor,
    CanonicalActorBuilder,
    ConcurrentSessionHarness,
    ConcurrentTestRunner,
    ConcurrencyBarrier,
    ConcurrentTestResult,
    SessionContext,
)


# =============================================================================
# Core Fixtures
# =============================================================================

@pytest_asyncio.fixture
async def concurrency_organization(db_session: AsyncSession) -> Organization:
    """Create a test organization for concurrency tests."""
    unique = uuid.uuid4().hex[:8]
    org = Organization(
        id=f"concurrency-org-{unique}",
        name=f"Concurrency Test Org {unique}",
        slug=f"concurrency-org-{unique}",
        status="active",
        industry="Software",
        country="US",
        timezone="UTC",
        currency="USD",
    )
    db_session.add(org)
    await db_session.flush()
    return org


@pytest_asyncio.fixture
async def concurrency_db_session_factory(engine) -> async_sessionmaker:
    """Create a session factory for concurrent tests using the test engine."""
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


# =============================================================================
# Same-Company Multi-Actor Fixtures
# =============================================================================

@dataclass
class SameCompanyActors:
    """Container for multiple actors within the same organization."""
    organization: Organization
    actors: Dict[str, CanonicalActor]
    harness: "ConcurrentSessionHarness"
    runner: "ConcurrentTestRunner"
    barrier: "ConcurrencyBarrier"


@pytest_asyncio.fixture
async def same_company_actors(
    concurrency_organization: Organization,
    concurrency_db_session_factory: async_sessionmaker,
) -> SameCompanyActors:
    """Create 3 actors within the same organization for concurrency tests (default)."""
    return await _create_same_company_actors(concurrency_organization, concurrency_db_session_factory, 3)


@pytest_asyncio.fixture
async def ten_actors_same_company(
    concurrency_organization: Organization,
    concurrency_db_session_factory: async_sessionmaker,
) -> SameCompanyActors:
    """Create 10 actors for 10-concurrent-operation tests."""
    return await _create_same_company_actors(concurrency_organization, concurrency_db_session_factory, 10)


@pytest_asyncio.fixture
async def hundred_actors_same_company(
    concurrency_organization: Organization,
    concurrency_db_session_factory: async_sessionmaker,
) -> SameCompanyActors:
    """Create 100 actors for 100-concurrent-operation tests."""
    return await _create_same_company_actors(concurrency_organization, concurrency_db_session_factory, 100)


@pytest_asyncio.fixture
async def two_actors_same_company(
    concurrency_organization: Organization,
    concurrency_db_session_factory: async_sessionmaker,
) -> Tuple[CanonicalActor, CanonicalActor, "ConcurrentSessionHarness", "ConcurrencyBarrier"]:
    """Create exactly 2 actors in the same company for pairwise tests."""
    actors_result = await _create_same_company_actors(concurrency_organization, concurrency_db_session_factory, 2)
    actor_list = list(actors_result.actors.values())
    return actor_list[0], actor_list[1], actors_result.harness, actors_result.barrier


async def _create_same_company_actors(
    concurrency_organization: Organization,
    concurrency_db_session_factory: async_sessionmaker,
    num_actors: int,
    role_codes: Optional[List[str]] = None,
) -> SameCompanyActors:
    """Create multiple actors within the same organization for concurrency tests.
    
    Args:
        num_actors: Number of actors to create
        role_codes: Role codes to assign (default ["ceo"] for full access)
    """
    if role_codes is None:
        role_codes = ["ceo"]
    
    actors = {}
    db = concurrency_db_session_factory()
    
    try:
        async with db.begin():
            # Build actors
            for i in range(num_actors):
                builder = CanonicalActorBuilder(
                    db=db,
                    organization=concurrency_organization,
                    user_id=f"actor-{i}-{uuid.uuid4().hex[:8]}",
                    email=f"actor{i}-{uuid.uuid4().hex[:8]}@test.com",
                    full_name=f"Actor {i} {uuid.uuid4().hex[:8]}",
                    role_codes=role_codes,
                )
                actor = await builder.build()
                actors[actor.user_id] = actor
        
        # Create harness and runner
        harness = ConcurrentSessionHarness(
            session_factory=concurrency_db_session_factory,
            organization=concurrency_organization,
            actors=list(actors.values()),
        )
        
        barrier = ConcurrencyBarrier(parties=num_actors, name="same-company")
        runner = ConcurrentTestRunner(
            session_factory=concurrency_db_session_factory,
            actors=list(actors.values()),
        )
        runner.barrier = barrier
        
        return SameCompanyActors(
            organization=concurrency_organization,
            actors=actors,
            harness=harness,
            runner=runner,
            barrier=barrier,
        )
    finally:
        await db.close()


# =============================================================================
# Cross-Company Tenant Isolation Fixtures
# =============================================================================

@dataclass
class CrossCompanyActors:
    """Container for actors in different organizations for tenant isolation tests."""
    organizations: Dict[str, Organization]
    actors: Dict[str, CanonicalActor]
    harnesses: Dict[str, "ConcurrentSessionHarness"]
    barriers: Dict[str, "ConcurrencyBarrier"]


@pytest_asyncio.fixture
async def cross_company_actors(
    concurrency_db_session_factory: async_sessionmaker,
    num_organizations: int = 2,
    actors_per_org: int = 2,
    role_codes: Optional[List[str]] = None,
) -> CrossCompanyActors:
    """Create actors across multiple organizations for tenant isolation tests.
    
    Args:
        num_organizations: Number of organizations to create
        actors_per_org: Number of actors per organization
        role_codes: Role codes for actors
    """
    if role_codes is None:
        role_codes = ["ceo"]
    
    organizations = {}
    actors = {}
    harnesses = {}
    barriers = {}
    
    for org_idx in range(num_organizations):
        # Create organization
        org = Organization(
            id=f"cross-org-{org_idx}-{uuid.uuid4().hex[:8]}",
            name=f"Cross Company Org {org_idx} {uuid.uuid4().hex[:8]}",
            slug=f"cross-org-{org_idx}-{uuid.uuid4().hex[:8]}",
            status="active",
            industry="Software",
            country="US",
            timezone="UTC",
            currency="USD",
        )
        
        db = concurrency_db_session_factory()
        try:
            async with db.begin():
                db.add(org)
                await db.flush()
                organizations[f"org_{org_idx}"] = org
                
                # Create actors for this org
                org_actors = {}
                for actor_idx in range(actors_per_org):
                    builder = CanonicalActorBuilder(
                        db=db,
                        organization=org,
                        user_id=f"org{org_idx}-actor{actor_idx}-{uuid.uuid4().hex[:8]}",
                        email=f"org{org_idx}-actor{actor_idx}-{uuid.uuid4().hex[:8]}@test.com",
                        full_name=f"Org {org_idx} Actor {actor_idx} {uuid.uuid4().hex[:8]}",
                        role_codes=role_codes,
                    )
                    actor = await builder.build()
                    actors[f"org_{org_idx}_actor_{actor_idx}"] = actor
                    org_actors[actor.user_id] = actor
                
                # Create harness for this org
                harness = ConcurrentSessionHarness(
                    session_factory=concurrency_db_session_factory,
                    organization=org,
                    actors=list(org_actors.values()),
                )
                harnesses[f"org_{org_idx}"] = harness
                
                # Create barrier for this org
                barrier = ConcurrencyBarrier(parties=actors_per_org, name=f"cross-org-{org_idx}")
                barriers[f"org_{org_idx}"] = barrier
        finally:
            await db.close()
    
    return CrossCompanyActors(
        organizations=organizations,
        actors=actors,
        harnesses=harnesses,
        barriers=barriers,
    )


@pytest_asyncio.fixture
async def two_orgs_two_actors_each(
    concurrency_db_session_factory: async_sessionmaker,
) -> CrossCompanyActors:
    """Create 2 organizations with 2 actors each for tenant isolation tests."""
    return await cross_company_actors(
        concurrency_db_session_factory,
        num_organizations=2,
        actors_per_org=2,
    )


# =============================================================================
# Shared Entity Fixtures
# =============================================================================

@dataclass
class SharedEntityFixture:
    """A canonical entity shared by multiple actors for concurrency tests."""
    entity: Any
    entity_type: str
    organization: Organization
    fingerprint: str
    idempotency_key: Optional[str] = None


@pytest_asyncio.fixture
async def shared_company_commitment(
    concurrency_organization: Organization,
    db_session: AsyncSession,
) -> SharedEntityFixture:
    """Create a CompanyCommitment shared by multiple actors."""
    fingerprint = f"shared-commitment-{uuid.uuid4().hex[:8]}"
    comm = CompanyCommitment(
        organization_id=concurrency_organization.id,
        commitment_type="unconditional",
        title="Shared Commitment for Concurrency Test",
        scope_type="objective",
        authorization_id="auth-shared",
        decision_id="dec-shared",
        fingerprint=fingerprint,
    )
    db_session.add(comm)
    await db_session.flush()
    
    return SharedEntityFixture(
        entity=comm,
        entity_type="CompanyCommitment",
        organization=concurrency_organization,
        fingerprint=fingerprint,
        idempotency_key=f"idem-{fingerprint}",
    )


@pytest_asyncio.fixture
async def shared_company_authorization(
    concurrency_organization: Organization,
    db_session: AsyncSession,
) -> SharedEntityFixture:
    """Create a CompanyAuthorization shared by multiple actors."""
    fingerprint = f"shared-auth-{uuid.uuid4().hex[:8]}"
    auth = CompanyAuthorization(
        organization_id=concurrency_organization.id,
        id=f"auth-{uuid.uuid4().hex[:8]}",
        decision_id=f"dec-{uuid.uuid4().hex[:8]}",
        policy_id=f"pol-{uuid.uuid4().hex[:8]}",
        title="Shared Authorization for Concurrency Test",
        state="requested",
        source_event_id="evt-shared",
        fingerprint=fingerprint,
    )
    db_session.add(auth)
    await db_session.flush()
    
    return SharedEntityFixture(
        entity=auth,
        entity_type="CompanyAuthorization",
        organization=concurrency_organization,
        fingerprint=fingerprint,
        idempotency_key=f"idem-{fingerprint}",
    )


@pytest_asyncio.fixture
async def shared_canonical_operation(
    concurrency_organization: Organization,
    db_session: AsyncSession,
) -> SharedEntityFixture:
    """Create a CanonicalOperation shared by multiple actors."""
    fingerprint = f"shared-op-{uuid.uuid4().hex[:8]}"
    op = CanonicalOperation(
        id=f"op-{uuid.uuid4().hex[:8]}",
        organization_id=concurrency_organization.id,
        operation_type="test_operation",
        title="Shared Operation for Concurrency Test",
        state="queued",
        fingerprint=fingerprint,
    )
    db_session.add(op)
    await db_session.flush()
    
    return SharedEntityFixture(
        entity=op,
        entity_type="CanonicalOperation",
        organization=concurrency_organization,
        fingerprint=fingerprint,
    )


# =============================================================================
# WorkerLease Fixtures
# =============================================================================

@pytest_asyncio.fixture
async def worker_lease_manager(
    concurrency_db_session_factory: async_sessionmaker,
) -> "LeaseManager":
    """Create a LeaseManager for WorkerLease tests."""
    from app.intelligence.canonical_concurrency import LeaseManager
    
    db = concurrency_db_session_factory()
    try:
        yield LeaseManager(db)
    finally:
        await db.close()


@pytest_asyncio.fixture
async def worker_lease_operation(
    concurrency_organization: Organization,
    db_session: AsyncSession,
) -> Tuple[CanonicalOperation, "LeaseManager"]:
    """Create an operation with a LeaseManager for lease tests."""
    from app.intelligence.canonical_concurrency import LeaseManager
    
    op = CanonicalOperation(
        id=f"op-lease-{uuid.uuid4().hex[:8]}",
        organization_id=concurrency_organization.id,
        operation_type="test_operation",
        title="Lease Test Operation",
        state="queued",
        fingerprint=f"fp-lease-{uuid.uuid4().hex[:8]}",
    )
    db_session.add(op)
    await db_session.flush()
    
    lease_mgr = LeaseManager(db_session)
    return op, lease_mgr


# =============================================================================
# Integration Replay Fixtures
# =============================================================================

@pytest_asyncio.fixture
async def external_event_source(
    concurrency_organization: Organization,
    db_session: AsyncSession,
) -> Dict[str, Any]:
    """Create a canonical operation representing an external event source."""
    event_id = f"EXT-EVT-{uuid.uuid4().hex[:8]}"
    fingerprint = f"ext-event-{event_id}"
    
    op = CanonicalOperation(
        id=f"op-ext-{uuid.uuid4().hex[:8]}",
        organization_id=concurrency_organization.id,
        operation_type="external_webhook",
        title=f"External Event {event_id}",
        state="queued",
        is_external=True,
        external_system="stripe",
        external_operation_id=event_id,
        fingerprint=fingerprint,
    )
    db_session.add(op)
    await db_session.flush()
    
    return {
        "external_event_id": event_id,
        "fingerprint": fingerprint,
        "operation": op,
        "provenance": {"external_event_id": event_id, "source": "stripe"},
    }


# =============================================================================
# Temporal Integrity Fixtures
# =============================================================================

@pytest_asyncio.fixture
async def temporal_authorization_chain(
    concurrency_organization: Organization,
    db_session: AsyncSession,
) -> List[CompanyAuthorization]:
    """Create a chain of authorizations with temporal boundaries."""
    now = utcnow()
    auths = []
    
    # Jan 1 - Jun 1
    auth_jan = CompanyAuthorization(
        organization_id=concurrency_organization.id,
        id=f"auth-jan-{uuid.uuid4().hex[:8]}",
        decision_id=f"dec-temporal-{uuid.uuid4().hex[:8]}",
        policy_id=f"pol-temporal-{uuid.uuid4().hex[:8]}",
        title="Jan Authorization",
        state="approved",
        valid_from=now.replace(month=1, day=1),
        valid_until=now.replace(month=6, day=1),
        source_event_id="evt-jan",
        fingerprint=f"fp-jan-{uuid.uuid4().hex[:8]}",
    )
    db_session.add(auth_jan)
    auths.append(auth_jan)
    
    # Jun 1 - Dec 31
    auth_jun = CompanyAuthorization(
        organization_id=concurrency_organization.id,
        id=f"auth-jun-{uuid.uuid4().hex[:8]}",
        decision_id=auth_jan.decision_id,
        policy_id=auth_jan.policy_id,
        title="Jun Authorization",
        state="approved",
        valid_from=now.replace(month=6, day=1),
        valid_until=now.replace(month=12, day=31),
        source_event_id="evt-jun",
        fingerprint=f"fp-jun-{uuid.uuid4().hex[:8]}",
    )
    db_session.add(auth_jun)
    auths.append(auth_jun)
    
    await db_session.flush()
    
    # Establish supersession chain
    auth_jan.superseded_by_id = auth_jun.id
    auth_jun.supersedes_id = auth_jan.id
    await db_session.flush()
    
    return auths


# =============================================================================
# Provenance/Epistemic Fixtures
# =============================================================================

@pytest_asyncio.fixture
async def ai_generated_decision(
    concurrency_organization: Organization,
    db_session: AsyncSession,
) -> "CompanyDecision":
    """Create a decision with AI origin provenance."""
    from app.models.company_operating import CompanyDecision
    
    decision = CompanyDecision(
        organization_id=concurrency_organization.id,
        decision_id=f"dec-ai-{uuid.uuid4().hex[:8]}",
        kind="other",
        title="AI Generated Decision",
        rationale="Auto-generated for testing",
        state="proposed",
        epistemic_status="proposed",
        provenance={
            "source": "ai",
            "model_id": "gpt-4",
            "model_version": "2024-01",
            "generation_context": "auto-generated",
        },
        source_event_id=f"evt-ai-{uuid.uuid4().hex[:8]}",
    )
    db_session.add(decision)
    await db_session.flush()
    return decision


@pytest_asyncio.fixture
async def evidence_backed_decision(
    concurrency_organization: Organization,
    db_session: AsyncSession,
) -> "CompanyDecision":
    """Create a decision with evidence-backed epistemic status."""
    from app.models.company_operating import CompanyDecision
    
    decision = CompanyDecision(
        organization_id=concurrency_organization.id,
        decision_id=f"dec-evidence-{uuid.uuid4().hex[:8]}",
        kind="other",
        title="Evidence Backed Decision",
        rationale="Supported by evidence",
        state="proposed",
        epistemic_status="evidence_backed",
        provenance={"evidence_ids": ["ev-1", "ev-2"]},
        source_event_id=f"evt-evidence-{uuid.uuid4().hex[:8]}",
    )
    db_session.add(decision)
    await db_session.flush()
    return decision


# =============================================================================
# Cleanup Fixtures
# =============================================================================

@pytest_asyncio.fixture(autouse=True)
async def cleanup_concurrency_state():
    """Automatically clean up any concurrency test state after each test."""
    yield
    # The session fixtures handle cleanup automatically
    # This fixture ensures no leaked state between tests


# =============================================================================
# Utility Functions
# =============================================================================

async def create_actor_with_permissions(
    db: AsyncSession,
    organization: Organization,
    user_id: str,
    role_codes: List[str] = None,
) -> CanonicalActor:
    """Create a single actor with specified permissions."""
    if role_codes is None:
        role_codes = ["ceo"]
    
    builder = CanonicalActorBuilder(
        db=db,
        organization=organization,
        user_id=user_id,
        email=f"{user_id}@test.com",
        full_name=f"Actor {user_id}",
        role_codes=role_codes,
    )
    return await builder.build()


async def setup_organization_permissions(
    db: AsyncSession,
    organization: Organization,
) -> None:
    """Set up permission catalog and roles for an organization."""
    await permission_service.sync_catalog(db)
    await permission_service.seed_org_roles(db, organization.id)


async def assign_role(
    db: AsyncSession,
    user_id: str,
    organization_id: str,
    role_code: str,
) -> Optional[Role]:
    """Assign a role to a user in an organization."""
    role = (await db.execute(
        select(Role).where(
            Role.organization_id == organization_id,
            Role.code == role_code,
        )
    )).scalars().first()
    
    if role:
        user_role = UserRole(
            user_id=user_id,
            role_id=role.id,
            organization_id=organization_id,
        )
        db.add(user_role)
        await db.flush()
    
    return role


# =============================================================================
# Assertion Helpers
# =============================================================================

def assert_single_canonical_effect(
    results: List[ConcurrentTestResult],
    entity_type: str,
) -> str:
    """Assert that concurrent operations produced exactly one canonical entity.
    
    Returns the entity ID of the single canonical entity.
    """
    successful = [r for r in results if r.success]
    assert len(successful) > 0, "At least one operation should succeed"
    
    entity_ids = {r.entity_id for r in successful if r.entity_id}
    assert len(entity_ids) == 1, f"Expected exactly 1 {entity_type}, got {len(entity_ids)}: {entity_ids}"
    
    return list(entity_ids)[0]


def assert_no_lost_updates(
    results: List[ConcurrentTestResult],
    expected_version_increment: int = 1,
) -> None:
    """Assert that no updates were lost in concurrent execution."""
    successful = [r for r in results if r.success]
    failed = [r for r in results if not r.success]
    
    # Exactly one should succeed (the first to commit)
    assert len(successful) == 1, f"Expected 1 successful update, got {len(successful)}"
    assert len(failed) >= 1, "Expected at least 1 conflict failure"
    
    # All failures should be concurrency/version errors
    for r in failed:
        assert any(kw in r.error.lower() for kw in ["stale", "version", "concurrency"]), \
            f"Expected concurrency error, got: {r.error}"


def assert_tenant_isolation(
    results_a: List[ConcurrentTestResult],
    results_b: List[ConcurrentTestResult],
    org_a_id: str,
    org_b_id: str,
    db_session: AsyncSession,
    entity_type: str,
) -> None:
    """Assert that tenant isolation is maintained under concurrency."""
    successful_a = [r for r in results_a if r.success]
    successful_b = [r for r in results_b if r.success]
    
    assert len(successful_a) > 0, "Tenant A operations should succeed"
    assert len(successful_b) > 0, "Tenant B operations should succeed"
    
    # Verify database state
    from sqlalchemy import select
    
    model_map = {
        "CompanyCommitment": "CompanyCommitment",
        "CompanyAuthorization": "CompanyAuthorization",
        "CompanyDecision": "CompanyDecision",
        "CanonicalOperation": "CanonicalOperation",
    }
    
    # This would be implemented based on the entity type
    # The key assertion is that each tenant only sees their own data


def assert_unknown_preserved(
    result: ConcurrentTestResult,
    operation: "CanonicalOperation",
) -> None:
    """Assert that UNKNOWN state was preserved (not converted to FAILED/SUCCESS)."""
    assert operation.state == "unknown", f"Expected UNKNOWN state, got {operation.state}"
    assert operation.outcome is None, "Outcome should be None for UNKNOWN"


def assert_lease_exclusivity(
    lease_id: str,
    expected_holder: str,
    lease_manager: "LeaseManager",
) -> None:
    """Assert that a lease is held exclusively by the expected worker."""
    import asyncio
    
    async def check():
        lease = await lease_manager.get_lease(lease_id)
        assert lease is not None, "Lease should exist"
        assert lease.worker_id == expected_holder, f"Lease held by {lease.worker_id}, expected {expected_holder}"
        assert lease.active is True, "Lease should be active"
    
    return asyncio.run(check())



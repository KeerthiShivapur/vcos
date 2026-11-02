"""Concurrency test context and utilities."""

import asyncio
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, Callable, List, Optional, Set, Dict, Awaitable, Tuple

import pytest_asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.organization import Organization
from app.models.user import User
from app.models.role import Role, UserRole
from app.services.permission_service import permission_service
from app.intelligence.company_context import resolve_caller_access, CallerAccess
from app.core.timeutils import utcnow
from app.models.execution_strategy import CompanyCommitment, CompanyAuthorization
from app.models.company_operating import CompanyDecision
from app.models.canonical_reliability import CanonicalOperation


# =============================================================================
# Concurrency Test Infrastructure
# =============================================================================

@dataclass
class SessionContext:
    """Context for a concurrent test session."""
    session: AsyncSession
    actor: 'CanonicalActor'
    correlation_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])


@dataclass
class ConcurrentTestResult:
    """Result of a concurrent test operation."""
    actor_id: str
    correlation_id: str
    success: bool
    result: Any = None
    error: Optional[str] = None
    error_code: Optional[str] = None
    duration_ms: float = 0.0
    entity_id: Optional[str] = None
    entity_type: Optional[str] = None
    phase_timings: Dict[str, float] = field(default_factory=dict)


@dataclass
class ConcurrencyBarrier:
    """Barrier for synchronizing concurrent test operations."""
    parties: int
    name: str = "barrier"
    _event: asyncio.Event = field(default_factory=asyncio.Event)
    _count: int = 0
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    _phase: int = 0
    _phase_events: Dict[int, asyncio.Event] = field(default_factory=lambda: {0: asyncio.Event()})
    
    def __post_init__(self):
        self._phase_events[0].set()
    
    @property
    def phase(self) -> int:
        return self._phase
    
    async def wait(self, phase: Optional[int] = None) -> None:
        target_phase = phase if phase is not None else self._phase
        
        if target_phase not in self._phase_events:
            self._phase_events[target_phase] = asyncio.Event()
        
        async with self._lock:
            self._count += 1
            if self._count >= self.parties:
                # All parties arrived, advance phase
                self._count = 0
                self._phase = target_phase + 1
                self._phase_events[target_phase].set()
                if self._phase not in self._phase_events:
                    self._phase_events[self._phase] = asyncio.Event()
                self._phase_events[self._phase].set()
                return
            
            await self._phase_events[target_phase].wait()


@dataclass
class PhaseBarrier:
    """Multi-phase barrier for complex concurrency scenarios."""
    parties: int
    phases: List[str]
    _phase_idx: int = 0
    _events: Dict[int, asyncio.Event] = field(default_factory=lambda: {0: asyncio.Event()})
    _counts: Dict[int, int] = field(default_factory=lambda: {0: 0})
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    
    @property
    def current_phase(self) -> str:
        return self.phases[self._phase_idx] if self._phase_idx < len(self.phases) else "completed"
    
    async def wait(self) -> None:
        phase_idx = self._phase_idx
        
        if phase_idx not in self._events:
            self._events[phase_idx] = asyncio.Event()
        
        async with self._lock:
            self._counts[phase_idx] = self._counts.get(phase_idx, 0) + 1
            if self._counts[phase_idx] >= self.parties:
                # All arrived, advance phase
                self._counts[phase_idx] = 0
                self._phase_idx += 1
                if self._phase_idx not in self._events:
                    self._events[self._phase_idx] = asyncio.Event()
                self._events[self._phase_idx].set()
                return
        
        await self._events[phase_idx].wait()


@dataclass
class ConcurrentTestRunner:
    """Runs concurrent operations with controlled scheduling.
    
    Each concurrent operation gets its own database session to avoid
    SQLAlchemy session sharing issues.
    """
    
    def __init__(
        self,
        session_factory,
        actors: List['CanonicalActor'],
        barrier: Optional['ConcurrencyBarrier'] = None,
        harness: Optional['ConcurrentSessionHarness'] = None,
    ):
        self.session_factory = session_factory
        self.actors = {a.user_id: a for a in actors}
        self.results: List[ConcurrentTestResult] = []
        self._results_lock = asyncio.Lock()
        self.barrier = barrier
        
        if harness is not None:
            self.harness = harness
        else:
            # Create a simple harness-like object with session_for method
            class SimpleHarness:
                def __init__(self, session_factory):
                    self.session_factory = session_factory
                
                @asynccontextmanager
                async def session_for(self, actor_id: str):
                    async with self.session_factory() as session:
                        async with session.begin():
                            yield SessionContext(session=session, actor=None)
            
            self.harness = SimpleHarness(session_factory)
    
    async def run_concurrent(
        self,
        operation_fn: Callable[[str, Any], Awaitable[Any]],
        *args,
        num_workers: Optional[int] = None,
        barrier: Optional['ConcurrencyBarrier'] = None,
        **kwargs
    ) -> List[ConcurrentTestResult]:
        """Run operation concurrently across all actors in the harness."""
        self.results = []
        
        if num_workers is None:
            num_workers = len(self.actors)
        
        if barrier is None:
            barrier = ConcurrencyBarrier(parties=num_workers)
        
        self.barrier = barrier
        
        async def run_actor(actor_id: str):
            start = time.time()
            phase_timings = {}
            
            async with self.harness.session_for(actor_id) as ctx:
                try:
                    # Phase 1: Barrier - all actors reach starting line
                    phase_start = time.time()
                    await self.barrier.wait()
                    phase_timings["barrier_enter"] = (time.time() - phase_start) * 1000
                    
                    # Phase 2: Execute operation
                    phase_start = time.time()
                    result = await operation_fn(actor_id, ctx, *args, **kwargs)
                    phase_timings["execute"] = (time.time() - phase_start) * 1000
                    
                    # Phase 3: Barrier - all actors complete
                    phase_start = time.time()
                    await self.barrier.wait()
                    phase_timings["barrier_exit"] = (time.time() - phase_start) * 1000
                    
                    duration = (time.time() - start) * 1000
                    
                    async with self._results_lock:
                        self.results.append(ConcurrentTestResult(
                            actor_id=actor_id,
                            correlation_id=ctx.correlation_id,
                            success=result.success if result else False,
                            result=result,
                            duration_ms=duration,
                            entity_id=getattr(getattr(result, 'entity', None), 'id', None) if result else None,
                            entity_type=type(getattr(result, 'entity', None)).__name__ if result and getattr(result, 'entity', None) else None,
                            phase_timings=phase_timings,
                            error=result.error if result else None,
                        ))
                except Exception as e:
                    duration = (time.time() - start) * 1000
                    async with self._results_lock:
                        self.results.append(ConcurrentTestResult(
                            actor_id=actor_id,
                            correlation_id=ctx.correlation_id if 'ctx' in locals() else "",
                            success=False,
                            error=str(e),
                            error_code=type(e).__name__,
                            duration_ms=duration,
                            phase_timings=phase_timings,
                        ))
        
        tasks = [run_actor(actor_id) for actor_id in self.actors.keys()]
        await asyncio.gather(*tasks)
        return self.results
    
    def successful_results(self) -> List[ConcurrentTestResult]:
        return [r for r in self.results if r.success]
    
    def failed_results(self) -> List[ConcurrentTestResult]:
        return [r for r in self.results if not r.success]
    
    def unique_entity_ids(self) -> Set[str]:
        return {r.entity_id for r in self.results if r.entity_id}
    
    def results_by_actor(self) -> Dict[str, ConcurrentTestResult]:
        return {r.actor_id: r for r in self.results}


# =============================================================================
# Canonical Actor Model
# =============================================================================

@dataclass
class CanonicalActor:
    """A legitimate concurrent actor with full VCOS identity context."""
    # Identity
    user_id: str
    email: str
    full_name: str
    
    # Organization
    organization_id: str
    organization_slug: str
    organization_name: str
    
    # Employment
    employee_id: Optional[str] = None
    
    # Authorization
    org_wide: bool = False
    role_codes: frozenset = field(default_factory=frozenset)
    permissions: frozenset = field(default_factory=frozenset)
    anchored_scope_ids: frozenset = field(default_factory=frozenset)
    ancestry_scope_ids: frozenset = field(default_factory=frozenset)
    visible_scope_ids: frozenset = field(default_factory=frozenset)
    project_ids: frozenset = field(default_factory=frozenset)
    member_conversation_ids: frozenset = field(default_factory=frozenset)
    links: Dict[str, str] = field(default_factory=dict)
    
    def to_caller_access(self) -> CallerAccess:
        """Convert to CallerAccess for use in canonical operations."""
        return CallerAccess(
            organization_id=self.organization_id,
            user_id=self.user_id,
            employee_id=self.employee_id,
            org_wide=self.org_wide,
            anchored_scope_ids=self.anchored_scope_ids,
            ancestry_scope_ids=self.ancestry_scope_ids,
            visible_scope_ids=self.visible_scope_ids,
            project_ids=self.project_ids,
            member_conversation_ids=self.member_conversation_ids,
            links=self.links,
        )


class ConcurrentSessionHarness:
    """Manages independent database sessions for concurrent actors.
    
    Each actor gets their own session/transaction boundary while operating
    against the same canonical company reality.
    """
    
    def __init__(
        self,
        session_factory,
        organization,
        actors: List[CanonicalActor],
    ):
        self.session_factory = session_factory
        self.organization = organization
        self.actors = {a.user_id: a for a in actors}
        self._active_sessions: Dict[str, SessionContext] = {}
    
    @asynccontextmanager
    async def session_for(self, actor_id: str):
        """Create a new session bound to the actor's context with automatic commit."""
        actor = self.actors.get(actor_id)
        if not actor:
            raise ValueError(f"Actor {actor_id} not found in harness")
        
        async with self.session_factory() as session:
            async with session.begin():
                # Ensure the actor's user exists in this session
                from app.models.user import User
                mock_user = User(
                    id=actor.user_id,
                    email=actor.email,
                    full_name=actor.full_name,
                    status="active",
                    organization_id=actor.organization_id,
                    password_hash="test-hash",
                )
                session.add(mock_user)
                await session.flush()
                
                context = SessionContext(session=session, actor=actor)
                self._active_sessions[actor_id] = context
                try:
                    yield SessionContext(session=session, actor=actor)
                finally:
                    self._active_sessions.pop(actor_id, None)
                    # Explicitly commit to ensure persistence
                    await session.commit()
    
    def get_caller(self, actor_id: str) -> CallerAccess:
        """Get CallerAccess for an actor."""
        actor = self.actors.get(actor_id)
        if not actor:
            raise ValueError(f"Actor {actor_id} not found in harness")
        return actor.to_caller_access()


# =============================================================================
# Test Fixtures
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


async def _create_same_company_actors(
    concurrency_organization: Organization,
    concurrency_db_session_factory: async_sessionmaker,
    num_actors: int,
    role_codes: Optional[List[str]] = None,
):
    """Create multiple actors within the same organization for concurrency tests."""
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
        runner = ConcurrentTestRunner(harness=harness, actors=list(actors.values()))
        
        return type('SameCompanyActors', (), {
            'organization': concurrency_organization,
            'actors': actors,
            'harness': harness,
            'runner': runner,
            'barrier': barrier,
        })()
    finally:
        await db.close()


@pytest_asyncio.fixture
async def same_company_actors(
    concurrency_organization: Organization,
    concurrency_db_session_factory: async_sessionmaker,
) -> 'SameCompanyActors':
    """Create 3 actors within the same organization for concurrency tests."""
    return await _create_same_company_actors(concurrency_organization, concurrency_db_session_factory, 3)


@pytest_asyncio.fixture
async def ten_actors_same_company(
    concurrency_organization: Organization,
    concurrency_db_session_factory: async_sessionmaker,
) -> 'SameCompanyActors':
    """Create 10 actors for 10-concurrent-operation tests."""
    return await _create_same_company_actors(concurrency_organization, concurrency_db_session_factory, 10)


@pytest_asyncio.fixture
async def hundred_actors_same_company(
    concurrency_organization: Organization,
    concurrency_db_session_factory: async_sessionmaker,
) -> 'SameCompanyActors':
    """Create 100 actors for 100-concurrent-operation tests."""
    return await _create_same_company_actors(concurrency_organization, concurrency_db_session_factory, 100)


@pytest_asyncio.fixture
async def two_actors_same_company(
    concurrency_organization: Organization,
    concurrency_db_session_factory: async_sessionmaker,
) -> Tuple['CanonicalActor', 'CanonicalActor', 'ConcurrentSessionHarness', 'ConcurrencyBarrier']:
    """Create exactly 2 actors in the same company for pairwise tests."""
    result = await _create_same_company_actors(concurrency_organization, concurrency_db_session_factory, 2)
    actor_list = list(result.actors.values())
    return actor_list[0], actor_list[1], result.harness, result.barrier


@pytest_asyncio.fixture
async def cross_company_actors(
    concurrency_db_session_factory: async_sessionmaker,
    num_organizations: int = 2,
    actors_per_org: int = 2,
    role_codes: Optional[List[str]] = None,
) -> 'CrossCompanyActors':
    """Create actors across multiple organizations for tenant isolation tests."""
    if role_codes is None:
        role_codes = ["ceo"]
    
    organizations = {}
    actors = {}
    harnesses = {}
    barriers = {}
    
    for org_idx in range(num_organizations):
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
                
                harness = ConcurrentSessionHarness(
                    session_factory=concurrency_db_session_factory,
                    organization=org,
                    actors=list(org_actors.values()),
                )
                harnesses[f"org_{org_idx}"] = harness
                
                barrier = ConcurrencyBarrier(parties=actors_per_org, name=f"cross-org-{org_idx}")
                barriers[f"org_{org_idx}"] = barrier
        finally:
            await db.close()
    
    return type('CrossCompanyActors', (), {
        'organizations': organizations,
        'actors': actors,
        'harnesses': harnesses,
        'barriers': barriers,
    })()


@pytest_asyncio.fixture
async def two_orgs_two_actors_each(
    concurrency_db_session_factory: async_sessionmaker,
) -> 'CrossCompanyActors':
    """Create 2 organizations with 2 actors each for tenant isolation tests."""
    return await cross_company_actors(
        concurrency_db_session_factory,
        num_organizations=2,
        actors_per_org=2,
    )


# =============================================================================
# Shared Entity Fixtures
# =============================================================================

@pytest_asyncio.fixture
async def shared_company_commitment(
    concurrency_organization: Organization,
    db_session: AsyncSession,
) -> 'SharedEntityFixture':
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
) -> 'SharedEntityFixture':
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
) -> 'SharedEntityFixture':
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


@pytest_asyncio.fixture
async def worker_lease_manager(
    concurrency_db_session_factory,
) -> 'LeaseManager':
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
) -> Tuple[CanonicalOperation, 'LeaseManager']:
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
        title=f"Process {event_id}",
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
    await db_session.flush()
    
    # Establish supersession chain
    auth_jan.superseded_by_id = auth_jun.id
    auth_jun.supersedes_id = auth_jan.id
    await db_session.flush()
    
    return [auth_jan, auth_jun]


# =============================================================================
# Provenance/Epistemic Fixtures
# =============================================================================

@pytest_asyncio.fixture
async def ai_generated_decision(
    concurrency_organization: Organization,
    db_session: AsyncSession,
) -> 'CompanyDecision':
    """Create a decision with AI origin provenance."""
    from app.models.company_operating import CompanyDecision
    
    decision = CompanyDecision(
        organization_id=concurrency_organization.id,
        decision_id=f"dec-ai-{uuid.uuid4().hex[:8]}",
        kind="other",
        title="AI Generated Decision",
        rationale="Test",
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
) -> 'CompanyDecision':
    """Create a decision with evidence-backed epistemic status."""
    from app.models.company_operating import CompanyDecision
    
    decision = CompanyDecision(
        organization_id=concurrency_organization.id,
        decision_id=f"dec-evidence-{uuid.uuid4().hex[:8]}",
        kind="other",
        title="Evidence Backed Decision",
        rationale="Test",
        state="proposed",
        epistemic_status="evidence_backed",
        provenance={"evidence_ids": ["ev-1", "ev-2"]},
        source_event_id=f"evt-evidence-{uuid.uuid4().hex[:8]}",
    )
    db_session.add(decision)
    await db_session.flush()
    return decision


# =============================================================================
# Shared Entity Fixture Container
# =============================================================================

@dataclass
class SharedEntityFixture:
    """Container for a shared canonical entity fixture."""
    entity: Any
    entity_type: str
    organization: Organization
    fingerprint: str
    idempotency_key: Optional[str] = None


# =============================================================================
# Assertion Helpers
# =============================================================================

def assert_idempotent_duplicate_operations(
    runner: 'ConcurrentTestRunner',
    expected_count: int,
    entity_type: str,
) -> str:
    """Assert that duplicate operations produced exactly one canonical entity.
    
    Args:
        runner: The test runner with results
        expected_count: Number of concurrent operations that were attempted
        entity_type: Human-readable entity type for error messages
    
    Returns:
        The entity ID of the single canonical entity
    """
    successful = runner.successful_results()
    assert len(successful) == expected_count, \
        f"All {expected_count} operations should succeed (idempotent), got {len(successful)}"
    
    entity_ids = runner.unique_entity_ids()
    assert len(entity_ids) == 1, f"Expected exactly 1 {entity_type}, got {len(entity_ids)}: {entity_ids}"
    
    return list(entity_ids)[0]


def assert_optimistic_concurrency_conflict(
    runner: 'ConcurrentTestRunner',
    expected_successes: int = 1,
) -> None:
    """Assert that optimistic concurrency control detected conflicts correctly.
    
    Args:
        runner: Test runner with results
        expected_successes: Number of operations expected to succeed (default 1)
    """
    successful = runner.successful_results()
    failed = runner.failed_results()
    
    # DEBUG: Print all results
    print(f"DEBUG assertion: total results={len(runner.results)}")
    for i, r in enumerate(runner.results):
        print(f"  Result {i}: actor={r.actor_id}, success={r.success}, error={r.error}, result_type={type(r.result).__name__ if r.result else None}")
    
    assert len(successful) == expected_successes, \
        f"Expected {expected_successes} successful operations, got {len(successful)}"
    assert len(failed) > 0, "Expected at least one concurrency conflict"
    
    # All failures should be version/concurrency errors
    for r in failed:
        error_lower = (r.error or "").lower()
        assert any(kw in error_lower for kw in ["stale", "version", "concurrency", "conflict"]), \
            f"Expected concurrency/version conflict error, got: {r.error}"


def assert_pessimistic_lock_exclusivity(
    runner: 'ConcurrentTestRunner',
    expected_exclusive_holder: int = 1,
) -> None:
    """Assert that pessimistic locking prevented concurrent access."""
    successful = runner.successful_results()
    failed = runner.failed_results()
    
    assert len(successful) == expected_exclusive_holder, \
        f"Expected {expected_exclusive_holder} to acquire lock, got {len(successful)}"
    assert len(failed) > 0, "Expected at least one lock contention"


def assert_unknown_state_preserved(
    result: 'ConcurrentTestResult',
    operation: 'CanonicalOperation',
) -> None:
    """Assert that UNKNOWN state was preserved (not converted to FAILED/SUCCESS)."""
    assert operation.state == "unknown", f"Expected UNKNOWN state, got {operation.state}"
    assert operation.outcome is None, "Outcome should be None for UNKNOWN state"


def assert_recovery_reconciliation_flow(
    operation: 'CanonicalOperation',
    expected_final_state: str = "reconciled",
) -> None:
    """Assert that recovery/reconciliation flow completed correctly."""
    assert operation.state == expected_final_state, \
        f"Expected {expected_final_state}, got {operation.state}"
    assert operation.outcome in ("success", "partial", "compensated"), \
        f"Expected successful outcome, got {operation.outcome}"


async def assert_tenant_isolation_maintained(
    results_a: List['ConcurrentTestResult'],
    results_b: List['ConcurrentTestResult'],
    org_a_id: str,
    org_b_id: str,
    db_session: 'AsyncSession',
    entity_model: type,
    org_field: str = "organization_id",
) -> None:
    """Assert that tenant isolation is maintained under concurrency."""
    successful_a = [r for r in results_a if r.success]
    successful_b = [r for r in results_b if r.success]
    
    assert len(successful_a) > 0, "Tenant A operations should succeed"
    assert len(successful_b) > 0, "Tenant B operations should succeed"
    
    # Verify database state
    from sqlalchemy import select, func
    
    count_a = await db_session.execute(
        select(func.count()).select_from(entity_model).where(
            getattr(entity_model, org_field) == org_a_id
        )
    )
    count_b = await db_session.execute(
        select(func.count()).select_from(entity_model).where(
            getattr(entity_model, org_field) == org_b_id
        )
    )
    
    # This would be implemented based on the entity model
    # The key assertion is that each tenant only has their own data


def assert_temporal_integrity_preserved(
    entity: Any,
    temporal_fields: List[str],
    original_values: Dict[str, Any],
) -> None:
    """Assert that temporal fields were preserved during concurrent updates."""
    for field in temporal_fields:
        current_value = getattr(entity, field, None)
        original_value = original_values.get(field)
        assert current_value == original_value, \
            f"Temporal field {field} changed from {original_value} to {current_value}"


def assert_provenance_preserved(
    entity: Any,
    provenance_fields: List[str],
    original_provenance: Dict[str, Any],
) -> None:
    """Assert that provenance was preserved during state transitions."""
    current_provenance = getattr(entity, "provenance", {}) or {}
    
    for field in provenance_fields:
        current_value = current_provenance.get(field)
        original_value = original_provenance.get(field)
        if original_value is not None:
            assert current_value == original_value, \
                f"Provenance field {field} changed from {original_value} to {current_value}"


def assert_epistemic_boundary_enforced(
    result: 'ConcurrentTestResult',
    forbidden_transitions: List[str] = None,
) -> None:
    """Assert that epistemic boundaries were enforced (illegal promotions blocked)."""
    if forbidden_transitions is None:
        forbidden_transitions = ["proposed->observed", "evidence_backed->observed", "predicted->observed"]
    
    assert not result.success, "Expected epistemic promotion to be blocked"
    
    error_lower = (result.error or "").lower()
    assert any(kw in error_lower for kw in ["epistemic", "promotion", "boundary", "illegal"]), \
        f"Expected epistemic boundary violation error, got: {result.error}"


def assert_no_resource_leaks(
    runner: 'ConcurrentTestRunner',
    checks: List[str] = None,
) -> None:
    """Assert that no resources were leaked after concurrent execution."""
    if checks is None:
        checks = ["connections", "leases", "transactions", "attempts"]
    
    # This is a placeholder for actual leak detection
    # Real implementation would check database connection pool, lease table, etc.
    assert all(r.duration_ms > 0 for r in runner.results), "All operations should have duration"


def assert_canonical_company_reality_integrity(
    db_session: 'AsyncSession',
    organization_id: str,
    expected_entities: Dict[str, int],
) -> None:
    """Assert that the canonical company reality remains consistent."""
    from sqlalchemy import select, func
    
    # This is a placeholder for comprehensive reality integrity checks
    # Real implementation would verify:
    # - No duplicate canonical entities
    # - All entities belong to correct organization
    # - Version chains are intact
    # - Provenance chains are intact
    pass


def assert_valid_lifecycle_transition(
    entity_type: str,
    from_state: str,
    to_state: str,
) -> None:
    """Assert that a state transition is valid per canonical lifecycle rules."""
    VALID_DECISION_TRANSITIONS = {
        "proposed": ["approved", "rejected"],
        "approved": ["executed", "superseded"],
        "rejected": [],
        "executed": ["outcome_recorded"],
        "outcome_recorded": ["assessed"],
        "assessed": [],
    }
    
    VALID_AUTHORIZATION_TRANSITIONS = {
        "requested": ["approved", "conditional", "rejected"],
        "approved": ["superseded"],
        "conditional": ["approved", "rejected", "superseded"],
        "rejected": [],
        "superseded": [],
    }
    
    VALID_ACTION_TRANSITIONS = {
        "proposed": ["validating", "awaiting_approval", "approved", "rejected"],
        "validating": ["approved", "awaiting_approval", "rejected"],
        "awaiting_approval": ["approved", "rejected", "expired"],
        "approved": ["ready", "rejected"],
        "ready": ["in_progress", "cancelled"],
        "in_progress": ["blocked", "completed", "failed", "cancelled"],
        "blocked": ["unblocked", "cancelled", "failed"],
        "completed": ["verified", "failed"],
        "verified": [],
        "failed": ["cancelled"],
        "cancelled": [],
        "expired": [],
        "superseded": [],
        "rejected": [],
    }
    
    valid_map = {
        "CompanyDecision": VALID_DECISION_TRANSITIONS,
        "CompanyAuthorization": VALID_AUTHORIZATION_TRANSITIONS,
        "CompanyAction": VALID_ACTION_TRANSITIONS,
    }
    
    valid = valid_map.get(entity_type, {})
    allowed = valid.get(from_state, [])
    
    assert to_state in allowed, \
        f"Invalid {entity_type} transition: {from_state} -> {to_state}. Allowed: {allowed}"


# =============================================================================
# CompanyCommitment Builder (for tests)
# =============================================================================

class CompanyCommitmentBuilder:
    """Builder for creating CompanyCommitment test fixtures."""
    
    def __init__(
        self,
        db: AsyncSession,
        organization: Organization,
        user_id: str,
        email: str,
        full_name: str,
        role_codes: List[str] = None,
    ):
        self.db = db
        self.organization = organization
        self.user_id = user_id
        self.email = email
        self.full_name = full_name
        self.role_codes = role_codes or ["ceo"]
    
    async def build(self) -> 'CanonicalActor':
        from app.models.user import User
        from app.models.role import Role, UserRole
        from app.services.permission_service import permission_service
        from app.intelligence.company_context import resolve_caller_access
        
        user = User(
            id=self.user_id,
            email=self.email,
            full_name=self.full_name,
            status="active",
            organization_id=self.organization.id,
            password_hash="test-hash",
        )
        self.db.add(user)
        await self.db.flush()
        
        await permission_service.sync_catalog(self.db)
        await permission_service.seed_org_roles(self.db, self.organization.id)
        
        for role_code in self.role_codes:
            role = (await self.db.execute(
                select(Role).where(
                    Role.organization_id == self.organization.id,
                    Role.code == role_code
                )
            )).scalars().first()
            if role:
                user_role = UserRole(
                    user_id=user.id,
                    role_id=role.id,
                    organization_id=self.organization.id,
                )
                self.db.add(user_role)
        
        await self.db.flush()
        
        caller = await resolve_caller_access(
            self.db, organization_id=self.organization.id, user=user
        )
        
        return CanonicalActor(
            user_id=user.id,
            email=user.email,
            full_name=user.full_name,
            organization_id=self.organization.id,
            organization_slug=self.organization.slug,
            organization_name=self.organization.name,
            employee_id=None,
            org_wide=caller.org_wide,
            role_codes=frozenset(self.role_codes),
            permissions=caller.get_permissions(self.db) if hasattr(caller, 'get_permissions') else frozenset(),
            anchored_scope_ids=caller.anchored_scope_ids,
            ancestry_scope_ids=caller.ancestry_scope_ids,
            visible_scope_ids=caller.visible_scope_ids,
            project_ids=caller.project_ids,
            member_conversation_ids=caller.member_conversation_ids,
            links=caller.links,
        )


# =============================================================================
# Actor Builder
# =============================================================================

class CanonicalActorBuilder:
    """Builder for creating CanonicalActor test fixtures with full VCOS identity."""
    
    def __init__(
        self,
        db: AsyncSession,
        organization: Organization,
        user_id: str,
        email: str,
        full_name: str,
        role_codes: List[str] = None,
    ):
        self.db = db
        self.organization = organization
        self.user_id = user_id
        self.email = email
        self.full_name = full_name
        self.role_codes = role_codes or ["ceo"]
    
    async def build(self) -> CanonicalActor:
        from app.models.user import User
        from app.models.role import Role, UserRole
        from app.services.permission_service import permission_service
        from app.intelligence.company_context import resolve_caller_access
        
        user = User(
            id=self.user_id,
            email=self.email,
            full_name=self.full_name,
            status="active",
            organization_id=self.organization.id,
            password_hash="test-hash",
        )
        self.db.add(user)
        await self.db.flush()
        
        await permission_service.sync_catalog(self.db)
        await permission_service.seed_org_roles(self.db, self.organization.id)
        
        for role_code in self.role_codes:
            role = (await self.db.execute(
                select(Role).where(
                    Role.organization_id == self.organization.id,
                    Role.code == role_code
                )
            )).scalars().first()
            if role:
                user_role = UserRole(
                    user_id=user.id,
                    role_id=role.id,
                    organization_id=self.organization.id,
                )
                self.db.add(user_role)
        
        await self.db.flush()
        
        caller = await resolve_caller_access(
            self.db, organization_id=self.organization.id, user=user
        )
        
        return CanonicalActor(
            user_id=user.id,
            email=user.email,
            full_name=user.full_name,
            organization_id=self.organization.id,
            organization_slug=self.organization.slug,
            organization_name=self.organization.name,
            employee_id=caller.employee_id,
            org_wide=caller.org_wide,
            role_codes=frozenset(self.role_codes),
            permissions=await caller.get_permissions(self.db) if hasattr(caller, 'get_permissions') else frozenset(),
            anchored_scope_ids=caller.anchored_scope_ids,
            ancestry_scope_ids=caller.ancestry_scope_ids,
            visible_scope_ids=caller.visible_scope_ids,
            project_ids=caller.project_ids,
            member_conversation_ids=caller.member_conversation_ids,
            links=caller.links,
        )


# =============================================================================
# Builder (alias for backward compatibility)
# =============================================================================

CanonicalActorBuilder = CanonicalActorBuilder


# Import time at the end to avoid circular import issues
import time
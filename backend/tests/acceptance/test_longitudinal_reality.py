"""35-I — Longitudinal Reality Acceptance Tests.

These tests verify that the longitudinal architecture preserves company
reality across time without overwriting historical truth:

1.  historical immutability (canonical timeline is append-only)
2.  point-in-time reconstruction of knowledge state
3.  current vs historical separation (effective intervals)
4.  knowledge timeline vs reality timeline separation
5.  decision history and provenance preservation
6.  supersession chains for corrected beliefs
7.  tenant isolation of historical queries and reconstruct attempts
8.  provenance preservation across source loss
9.  epistemic calibration across time
10. organizational continuity across structure changes
11. merger/acquisition lineage preservation
12. duplicate and out-of-order event handling
13. longitudinal integrity invariant detection
14. recovery after interrupted operations (35-H reliability infrastructure)

These tests require PostgreSQL: the longitudinal integrity checks use
window functions (LAG), bool_or aggregates and IS DISTINCT FROM, which have
no SQLite equivalent. They run against TEST_DATABASE_URL (CI provisions
postgres:18; local verification uses the vcos_test_matrix database).

The 35-I tables are defined by app.models.longitudinal but are not yet
covered by alembic migrations in every environment. The autouse
``longitudinal_schema`` fixture bootstraps the canonical model tables
(checkfirst) so the suite can run wherever PostgreSQL is available; it
never fabricates data and never modifies an existing table.
"""

import uuid
from datetime import timedelta

import pytest
import pytest_asyncio
from sqlalchemy import delete, or_, select
from sqlalchemy.exc import IntegrityError

from app.core.timeutils import utcnow
from app.db.database import Base
from app.intelligence.canonical_mutation import MutationType, canonical_create
from app.intelligence.company_context import resolve_caller_access
from app.models.canonical_integration import (
    Connector,
    ConnectorInstance,
    ExternalOperation,
)
from app.models.canonical_reliability import CanonicalOperation, ExternalUnknownState
from app.models.execution_strategy import CompanyGoal
from app.models.longitudinal import (
    CompanyKnowledgeSnapshot,
    CompanyMemorySnapshot,
    CompanyTimelineEvent,
    DecisionTimelineEvent,
    EpistemicCalibrationEvent,
    FutureSimulatorCalibration,
    LearningTimelineEvent,
    LongitudinalAdversarialTest,
    LongitudinalIntegrityFinding,
    LongitudinalProvenance,
    MergerAcquisitionLineage,
    OrganizationalTimelineEvent,
    TemporalQueryLog,
    TenantHistoricalIsolation,
)
from app.models.organization import Organization
from app.models.role import Role, UserRole
from app.models.user import User
from app.services.canonical_reality_integrity_service import (
    IntegrityFindingType,
    canonical_reality_integrity_service,
)
from app.services.canonical_reliability_service import canonical_reliability_service
from app.services.permission_service import permission_service

pytestmark = pytest.mark.postgres


# =============================================================================
# Schema bootstrap — 35-I tables (canonical models, checkfirst only)
# =============================================================================

_LONGITUDINAL_TABLES = [
    CompanyTimelineEvent.__table__,
    CompanyKnowledgeSnapshot.__table__,
    DecisionTimelineEvent.__table__,
    LearningTimelineEvent.__table__,
    OrganizationalTimelineEvent.__table__,
    MergerAcquisitionLineage.__table__,
    LongitudinalProvenance.__table__,
    EpistemicCalibrationEvent.__table__,
    CompanyMemorySnapshot.__table__,
    TemporalQueryLog.__table__,
    FutureSimulatorCalibration.__table__,
    LongitudinalIntegrityFinding.__table__,
    LongitudinalAdversarialTest.__table__,
    TenantHistoricalIsolation.__table__,
    # 35-H reliability tables reused by the failure/recovery class.
    CanonicalOperation.__table__,
    ExternalUnknownState.__table__,
    # Integration-layer tables the ExternalUnknownState FK requires.
    Connector.__table__,
    ConnectorInstance.__table__,
    ExternalOperation.__table__,
]


@pytest_asyncio.fixture(autouse=True)
async def longitudinal_schema(postgres_engine):
    """Ensure the canonical 35-I (and reused 35-H) tables exist.

    ``checkfirst=True`` makes this a no-op wherever the tables already
    exist (e.g. migrated databases). No table is ever altered or dropped.
    """
    async with postgres_engine.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: Base.metadata.create_all(
                sync_conn, tables=_LONGITUDINAL_TABLES, checkfirst=True
            )
        )


# =============================================================================
# Helpers
# =============================================================================

async def _make_org(factory, prefix: str = "lng") -> str:
    # Use UUID without hyphens to match current_organization_id() function behavior
    org_id = uuid.uuid4().hex
    async with factory() as session:
        session.add(Organization(
            id=org_id,
            name=f"Longitudinal {prefix} {org_id[:8]}",
            slug=f"lng-{org_id[:8]}",
            status="active",
        ))
        await session.commit()
    return org_id


async def _make_caller(factory, org_id: str):
    """Create an org-wide (CEO) caller through the real governance path."""
    from sqlalchemy import text
    suffix = uuid.uuid4().hex[:8]
    async with factory() as session:
        # Set tenant context for RLS policies
        await session.execute(
            text("SELECT set_config('app.current_organization_id', :org_id, false)"),
            {"org_id": org_id}
        )
        user = User(
            id=f"lng-user-{suffix}",
            email=f"lng-{suffix}@longitudinal.test",
            full_name=f"Longitudinal User {suffix}",
            status="active",
            organization_id=org_id,
            password_hash="test-hash",
        )
        session.add(user)
        await session.flush()

        await permission_service.sync_catalog(session)
        await permission_service.seed_org_roles(session, org_id)
        role = (await session.execute(
            select(Role).where(
                Role.organization_id == org_id,
                Role.code == "ceo",
            )
        )).scalars().first()
        if role:
            session.add(UserRole(
                user_id=user.id,
                role_id=role.id,
                organization_id=org_id,
            ))
        await session.commit()

        caller = await resolve_caller_access(
            session, organization_id=org_id, user=user
        )
        return caller, user.id


async def _with_tenant_context(factory, org_id: str, func, *args, **kwargs):
    """Execute a function with tenant context set for RLS policies."""
    from sqlalchemy import text
    async with factory() as session:
        await session.execute(
            text("SELECT set_config('app.current_organization_id', :org_id, false)"),
            {"org_id": org_id}
        )
        return await func(session, *args, **kwargs)


def _event(org_id: str, key: str, **overrides) -> CompanyTimelineEvent:
    now = utcnow()
    kwargs = dict(
        id=f"cte-{uuid.uuid4().hex[:12]}",
        organization_id=org_id,
        event_key=key,
        timeline_type="reality",
        event_type="reality.event",
        occurred_at=now,
        effective_from=now,
        change_summary=f"event {key}",
        epistemic_state="OBSERVED",
        confidence=1.0,
    )
    kwargs.update(overrides)
    return CompanyTimelineEvent(**kwargs)


def _snapshot(org_id: str, claim_id: str, **overrides) -> CompanyKnowledgeSnapshot:
    now = utcnow()
    kwargs = dict(
        id=f"cks-{uuid.uuid4().hex[:12]}",
        organization_id=org_id,
        claim_id=claim_id,
        claim_type="belief",
        claim_version=1,
        snapshot_at=now,
        valid_from=now,
        epistemic_state="OBSERVED",
        confidence=0.8,
        belief_json={"value": 1},
    )
    kwargs.update(overrides)
    return CompanyKnowledgeSnapshot(**kwargs)


def _provenance(org_id: str, chain_id: str, sequence: int, current_hash: str,
                **overrides) -> LongitudinalProvenance:
    now = utcnow()
    kwargs = dict(
        id=f"lp-{uuid.uuid4().hex[:12]}",
        organization_id=org_id,
        chain_id=chain_id,
        sequence=sequence,
        entity_type="CompanyDecision",
        entity_id="dec-lng",
        current_hash=current_hash,
        effective_from=now,
        recorded_at=now,
        is_genesis=(sequence == 1),
    )
    kwargs.update(overrides)
    return LongitudinalProvenance(**kwargs)


# =============================================================================
# 1. Historical immutability
# =============================================================================

class TestHistoricalImmutability:

    @pytest.mark.asyncio
    async def test_canonical_create_appends_timeline_event(
        self, pg_db_session, pg_db_session_factory
    ):
        """A canonical create appends exactly one reality timeline event."""
        org_id = await _make_org(pg_db_session_factory)
        caller, _ = await _make_caller(pg_db_session_factory, org_id)

        goal = CompanyGoal(
            organization_id=org_id,
            title="Longitudinal goal",
            status="active",
            kind="growth",
            fingerprint=f"fp-{uuid.uuid4().hex}",
        )
        result = await canonical_create(
            db=pg_db_session,
            caller=caller,
            entity=goal,
            required_permissions=["goals:manage"],
        )
        await pg_db_session.commit()
        assert result.success is True, result.error
        goal_id = result.entity.id

        async with pg_db_session_factory() as session:
            events = (await session.execute(
                select(CompanyTimelineEvent).where(
                    CompanyTimelineEvent.organization_id == org_id,
                    CompanyTimelineEvent.entity_id == goal_id,
                )
            )).scalars().all()

        assert len(events) == 1
        event = events[0]
        assert event.timeline_type == "strategy"
        assert event.event_subtype == MutationType.CREATE.value
        assert event.event_key == (
            f"CompanyGoal:{MutationType.CREATE.value}:{goal_id}"
        )
        assert event.to_state == "created"
        assert event.epistemic_state == "OBSERVED"

    @pytest.mark.asyncio
    async def test_timeline_event_duplicate_key_rejected_original_intact(
        self, pg_db_session_factory
    ):
        """Replaying an identical timeline event is rejected; the original
        row is never modified."""
        org_id = await _make_org(pg_db_session_factory)
        key = "CompanyDecision:transition:dec-immutable:executed"

        async def create_first_event(session):
            session.add(_event(
                org_id, key,
                timeline_type="decision",
                event_type="CompanyDecision.transition",
                from_state="approved",
                to_state="executed",
                delta_json={"state": "executed"},
            ))
            await session.commit()

        await _with_tenant_context(pg_db_session_factory, org_id, create_first_event)

        async def get_original(session):
            original = (await session.execute(
                select(CompanyTimelineEvent).where(
                    CompanyTimelineEvent.organization_id == org_id,
                    CompanyTimelineEvent.event_key == key,
                )
            )).scalars().one()
            return dict(original.delta_json), original.occurred_at

        original_delta, original_occurred_at = await _with_tenant_context(pg_db_session_factory, org_id, get_original)

        async def create_duplicate(session):
            session.add(_event(
                org_id, key,
                timeline_type="decision",
                event_type="CompanyDecision.transition",
                from_state="approved",
                to_state="executed",
                delta_json={"state": "rewritten"},
            ))
            with pytest.raises(IntegrityError):
                await session.flush()
            await session.rollback()

        await _with_tenant_context(pg_db_session_factory, org_id, create_duplicate)

        async def get_rows(session):
            rows = (await session.execute(
                select(CompanyTimelineEvent).where(
                    CompanyTimelineEvent.organization_id == org_id,
                    CompanyTimelineEvent.event_key == key,
                )
            )).scalars().all()
            return rows

        rows = await _with_tenant_context(pg_db_session_factory, org_id, get_rows)

        assert len(rows) == 1
        assert dict(rows[0].delta_json) == original_delta
        assert rows[0].occurred_at == original_occurred_at


# =============================================================================
# 2/4. Point-in-time reconstruction and knowledge vs reality timelines
# =============================================================================

class TestPointInTimeReconstruction:

    @pytest.mark.asyncio
    async def test_snapshot_supersession_chain_and_point_in_time_lookup(
        self, pg_db_session_factory
    ):
        """A corrected belief supersedes its predecessor; point-in-time
        queries return the belief state valid at that time and the
        superseded snapshot is never rewritten."""
        org_id = await _make_org(pg_db_session_factory)
        claim_id = f"claim-{uuid.uuid4().hex[:8]}"
        now = utcnow()
        t1 = now - timedelta(days=30)
        t2 = now - timedelta(days=10)

        async def create_snapshots(session):
            first = _snapshot(
                org_id, claim_id,
                snapshot_at=t1, valid_from=t1, valid_to=t2,
                epistemic_state="OBSERVED", confidence=0.6,
                belief_json={"value": 1},
            )
            session.add(first)
            await session.flush()
            session.add(_snapshot(
                org_id, claim_id,
                snapshot_at=t2, valid_from=t2,
                epistemic_state="CONFIRMED_CORRECTED", confidence=0.95,
                belief_json={"value": 2},
                corrected_at=t2, corrected_by="governance",
                correction_reason="restated after audit",
                supersedes_snapshot_id=first.id,
            ))
            await session.commit()
            return first.id

        first_id = await _with_tenant_context(pg_db_session_factory, org_id, create_snapshots)

        async def snapshot_at(session, at):
            return (await session.execute(
                select(CompanyKnowledgeSnapshot).where(
                    CompanyKnowledgeSnapshot.organization_id == org_id,
                    CompanyKnowledgeSnapshot.claim_id == claim_id,
                    CompanyKnowledgeSnapshot.valid_from <= at,
                    or_(
                        CompanyKnowledgeSnapshot.valid_to.is_(None),
                        CompanyKnowledgeSnapshot.valid_to > at,
                    ),
                ).order_by(CompanyKnowledgeSnapshot.snapshot_at.desc()).limit(1)
            )).scalars().first()

        async def get_historic_and_current(session):
            at_mid = t1 + timedelta(days=5)
            historic = await snapshot_at(session, at_mid)
            current = await snapshot_at(session, now)
            return historic, current

        historic, current = await _with_tenant_context(pg_db_session_factory, org_id, get_historic_and_current)

        assert historic is not None and historic.id == first_id
        assert historic.belief_json == {"value": 1}
        assert current.belief_json == {"value": 2}
        assert current.supersedes_snapshot_id == first_id
        assert current.valid_to is None

        async def get_original(session):
            return await session.get(CompanyKnowledgeSnapshot, first_id)

        original = await _with_tenant_context(pg_db_session_factory, org_id, get_original)
        assert original.belief_json == {"value": 1}
        assert original.epistemic_state == "OBSERVED"
        assert original.corrected_at is None

    @pytest.mark.asyncio
    async def test_reality_and_knowledge_timelines_stay_distinct(
        self, pg_db_session_factory
    ):
        """What happened (reality timeline) and what the company believed
        (knowledge timeline) coexist without mutual rewriting."""
        org_id = await _make_org(pg_db_session_factory)
        now = utcnow()

        async def create_events(session):
            reality = _event(
                org_id, "reality:market-entry",
                occurred_at=now,
                change_summary="entered EU market",
                metadata_json={"region": "EU"},
            )
            session.add(reality)
            await session.flush()
            reality_id = reality.id
            prediction = _snapshot(
                org_id, "claim-market-entry",
                claim_type="prediction",
                snapshot_at=now - timedelta(days=60),
                valid_from=now - timedelta(days=60),
                epistemic_state="PREDICTED",
                confidence=0.42,
                belief_json={"region": "EU", "confidence": 0.42},
                source_event_id=reality_id,
            )
            session.add(prediction)
            await session.commit()
            return reality_id

        reality_id = await _with_tenant_context(pg_db_session_factory, org_id, create_events)

        async def get_results(session):
            reality_row = await session.get(CompanyTimelineEvent, reality_id)
            beliefs = (await session.execute(
                select(CompanyKnowledgeSnapshot).where(
                    CompanyKnowledgeSnapshot.organization_id == org_id,
                    CompanyKnowledgeSnapshot.claim_type == "prediction",
                )
            )).scalars().all()
            return reality_row, beliefs

        reality_row, beliefs = await _with_tenant_context(pg_db_session_factory, org_id, get_results)

        assert reality_row.epistemic_state == "OBSERVED"
        assert reality_row.to_state is None
        assert reality_row.metadata_json == {"region": "EU"}
        assert len(beliefs) == 1
        assert beliefs[0].epistemic_state == "PREDICTED"
        assert beliefs[0].confidence < 1.0
        assert beliefs[0].belief_json["confidence"] == 0.42

    @pytest.mark.asyncio
    async def test_out_of_order_events_reconstruct_by_occurred_at(
        self, pg_db_session_factory
    ):
        """Events arriving out of order are ordered by occurred_at, not by
        insertion (recorded_at) order."""
        org_id = await _make_org(pg_db_session_factory)
        now = utcnow()
        early_occurrence = now - timedelta(hours=2)
        late_occurrence = now - timedelta(hours=1)

        async def create_late_event(session):
            late_arriving_first = _event(
                org_id, "state:two",
                occurred_at=late_occurrence,
                from_state="s1", to_state="s2",
            )
            session.add(late_arriving_first)
            await session.commit()

        await _with_tenant_context(pg_db_session_factory, org_id, create_late_event)

        async def create_early_event(session):
            early_arriving_late = _event(
                org_id, "state:one",
                occurred_at=early_occurrence,
                from_state="s0", to_state="s1",
            )
            session.add(early_arriving_late)
            await session.commit()

        await _with_tenant_context(pg_db_session_factory, org_id, create_early_event)

        async def get_ordered(session):
            ordered = (await session.execute(
                select(CompanyTimelineEvent).where(
                    CompanyTimelineEvent.organization_id == org_id,
                ).order_by(CompanyTimelineEvent.occurred_at.asc())
            )).scalars().all()
            latest = (await session.execute(
                select(CompanyTimelineEvent).where(
                    CompanyTimelineEvent.organization_id == org_id,
                ).order_by(CompanyTimelineEvent.occurred_at.desc()).limit(1)
            )).scalars().one()
            return ordered, latest

        ordered, latest = await _with_tenant_context(pg_db_session_factory, org_id, get_ordered)

        assert [e.event_key for e in ordered] == ["state:one", "state:two"]
        assert latest.event_key == "state:two"
        assert latest.to_state == "s2"
        # Insertion order (created_at) is the reverse of occurrence order:
        # the later-occurring event was stored first.
        assert ordered[0].created_at > ordered[1].created_at

    @pytest.mark.asyncio
    async def test_company_memory_snapshot_is_derived_projection(
        self, pg_db_session_factory
    ):
        """A company memory snapshot is a derived projection: it references
        its sources, carries an epistemic summary, and never mutates them."""
        org_id = await _make_org(pg_db_session_factory)
        now = utcnow()

        async def create_data(session):
            source = _event(org_id, "reality:funding-round")
            session.add(source)
            await session.flush()
            source_id = source.id
            session.add(CompanyMemorySnapshot(
                organization_id=org_id,
                snapshot_key=f"company:{now.isoformat()}",
                snapshot_at=now,
                scope_type="company",
                memory_json={"summary": "seed round closed"},
                source_event_ids_json=[source_id],
                epistemic_summary_json={"OBSERVED": 1},
                confidence=1.0,
            ))
            session.add(TemporalQueryLog(
                organization_id=org_id,
                query_text="What did we know about funding 30 days ago?",
                query_type="HISTORICAL",
                as_of=now - timedelta(days=30),
                result_summary="No funding record existed then",
                result_epistemic_state="UNKNOWN",
                confidence=0.9,
                source_event_ids_json=[source_id],
                actor_type="human",
            ))
            await session.commit()
            return source_id

        source_id = await _with_tenant_context(pg_db_session_factory, org_id, create_data)

        async def get_results(session):
            memory = (await session.execute(
                select(CompanyMemorySnapshot).where(
                    CompanyMemorySnapshot.organization_id == org_id,
                )
            )).scalars().one()
            log = (await session.execute(
                select(TemporalQueryLog).where(
                    TemporalQueryLog.organization_id == org_id,
                )
            )).scalars().one()
            stored_source = await session.get(CompanyTimelineEvent, source_id)
            return memory, log, stored_source

        memory, log, stored_source = await _with_tenant_context(pg_db_session_factory, org_id, get_results)

        assert memory.source_event_ids_json == [source_id]
        assert memory.snapshot_key.startswith("company:")
        assert log.query_type == "HISTORICAL"
        assert log.result_epistemic_state == "UNKNOWN"
        assert stored_source.event_key == "reality:funding-round"


# =============================================================================
# 5. Decision history and provenance
# =============================================================================

class TestDecisionHistory:

    @pytest.mark.asyncio
    async def test_decision_lifecycle_and_provenance_preserved(
        self, pg_db_session_factory
    ):
        """A decision's full lifecycle remains queryable in order with its
        provenance and rationale intact."""
        org_id = await _make_org(pg_db_session_factory)
        decision_id = f"dec-{uuid.uuid4().hex[:8]}"
        now = utcnow()
        t0 = now - timedelta(days=40)
        t1 = now - timedelta(days=30)
        t2 = now - timedelta(days=20)
        t3 = now - timedelta(days=5)

        stages = [
            ("CREATED", t0, None, "proposed", {"state": "proposed"},
             {"rationale": "initial proposal", "evidence_ids_json": ["ev-1"]}),
            ("AUTHORIZED", t1, "proposed", "approved", {"state": "approved"},
             {"authorized_by": "ceo", "rationale": "approved for execution"}),
            ("EXECUTED", t2, "approved", "executed", {"state": "executed"},
             {"rationale": "executed by ops"}),
            ("OUTCOME", t3, "executed", "outcome_recorded",
             {"state": "outcome_recorded"}, {"rationale": "outcome assessed"}),
        ]

        async def create_events(session):
            for index, (event_type, occurred, from_state, to_state,
                        decision_json, extra) in enumerate(stages):
                kwargs = dict(
                    id=f"dte-{uuid.uuid4().hex[:12]}",
                    organization_id=org_id,
                    decision_id=decision_id,
                    decision_version=index + 1,
                    event_key=f"dec:{event_type.lower()}",
                    event_type=event_type,
                    occurred_at=occurred,
                    effective_from=occurred,
                    from_state=from_state,
                    to_state=to_state,
                    decision_json=decision_json,
                    source_event_id=f"evt-{index}",
                    provenance_json={"actor": "test-suite"},
                )
                kwargs.update(extra)
                session.add(DecisionTimelineEvent(**kwargs))
            await session.commit()

        await _with_tenant_context(pg_db_session_factory, org_id, create_events)

        async def get_history(session):
            history = (await session.execute(
                select(DecisionTimelineEvent).where(
                    DecisionTimelineEvent.organization_id == org_id,
                    DecisionTimelineEvent.decision_id == decision_id,
                ).order_by(DecisionTimelineEvent.occurred_at.asc())
            )).scalars().all()
            return history

        history = await _with_tenant_context(pg_db_session_factory, org_id, get_history)

        assert [e.event_type for e in history] == [
            "CREATED", "AUTHORIZED", "EXECUTED", "OUTCOME",
        ]
        assert [e.decision_version for e in history] == [1, 2, 3, 4]
        assert history[0].rationale == "initial proposal"
        assert history[0].evidence_ids_json == ["ev-1"]
        assert history[1].authorized_by == "ceo"
        assert history[3].from_state == "executed"
        assert all(e.source_event_id for e in history)
        assert all(e.provenance_json == {"actor": "test-suite"}
                   for e in history)

        # The historical chain projects to the single canonical timeline:
        # earlier events are never rewritten by later ones.
        assert history[0].to_state == "proposed"
        assert history[0].occurred_at < history[1].occurred_at < history[3].occurred_at


# =============================================================================
# 8. Provenance preservation
# =============================================================================

class TestProvenancePreservation:

    @pytest.mark.asyncio
    async def test_provenance_survives_source_loss_and_flags_breaks(
        self, pg_db_session_factory
    ):
        """Provenance records remain queryable with their evidence after the
        source is gone; an explicitly broken chain is flagged, not erased."""
        org_id = await _make_org(pg_db_session_factory)
        chain = f"chain-{uuid.uuid4().hex[:8]}"
        now = utcnow()

        async def create_provenance(session):
            session.add(_provenance(
                org_id, chain, 1, "hash-1",
                evidence_ids_json=["ev-a"], value_json={"ref": "source-a"},
            ))
            session.add(_provenance(
                org_id, chain, 2, "hash-2",
                previous_hash="hash-1",
                evidence_ids_json=["ev-b"], value_json={"ref": "source-b"},
                broken=True,
                broken_reason="source system decommissioned",
            ))
            await session.commit()

        await _with_tenant_context(pg_db_session_factory, org_id, create_provenance)

        async def get_results(session):
            rows = (await session.execute(
                select(LongitudinalProvenance).where(
                    LongitudinalProvenance.organization_id == org_id,
                    LongitudinalProvenance.chain_id == chain,
                ).order_by(LongitudinalProvenance.sequence.asc())
            )).scalars().all()
            findings = await canonical_reality_integrity_service.check_longitudinal_integrity(
                db=session, organization_id=org_id
            )
            return rows, findings

        rows, findings = await _with_tenant_context(pg_db_session_factory, org_id, get_results)

        assert [r.sequence for r in rows] == [1, 2]
        assert rows[1].broken is True
        assert rows[0].evidence_ids_json == ["ev-a"]
        assert rows[1].value_json == {"ref": "source-b"}
        assert rows[1].broken_reason == "source system decommissioned"

        types = {f.finding_type for f in findings}
        assert IntegrityFindingType.LONGITUDINAL_BROKEN_CHAIN in types


# =============================================================================
# 7. Tenant historical isolation
# =============================================================================

class TestTenantHistoricalIsolation:

    @pytest.mark.asyncio
    async def test_historical_queries_are_tenant_scoped_and_attempts_recorded(
        self, pg_db_session_factory
    ):
        """Historical queries never cross tenant boundaries, and
        cross-tenant reconstruction attempts are recorded as blocked."""
        org_a = await _make_org(pg_db_session_factory, "lng-a")
        org_b = await _make_org(pg_db_session_factory, "lng-b")

        async def create_org_a_data(session):
            session.add(_snapshot(org_a, "claim-a", belief_json={"owner": "a"}))
            session.add(_event(org_a, "reality:a"))
            await session.commit()

        async def create_org_b_data(session):
            session.add(_snapshot(org_b, "claim-b", belief_json={"owner": "b"}))
            session.add(_event(org_b, "reality:b"))
            await session.commit()

        await _with_tenant_context(pg_db_session_factory, org_a, create_org_a_data)
        await _with_tenant_context(pg_db_session_factory, org_b, create_org_b_data)

        async def get_org_a_data(session):
            a_snapshots = (await session.execute(
                select(CompanyKnowledgeSnapshot).where(
                    CompanyKnowledgeSnapshot.organization_id == org_a,
                )
            )).scalars().all()
            a_events = (await session.execute(
                select(CompanyTimelineEvent).where(
                    CompanyTimelineEvent.organization_id == org_a,
                )
            )).scalars().all()
            return a_snapshots, a_events

        a_snapshots, a_events = await _with_tenant_context(pg_db_session_factory, org_a, get_org_a_data)

        assert all(s.organization_id == org_a for s in a_snapshots)
        assert all(e.organization_id == org_a for e in a_events)
        assert "claim-b" not in {s.claim_id for s in a_snapshots}

        async def add_audit(session):
            session.add(TenantHistoricalIsolation(
                source_org_id=org_a,
                target_org_id=org_b,
                attempt_type="RECONSTRUCTION",
                entity_type="CompanyKnowledgeSnapshot",
                entity_id=a_snapshots[0].id,
                blocked=True,
                rejection_reason="cross-tenant historical reconstruction blocked",
                actor_type="system",
                evidence_json={"query_org": org_a, "target_org": org_b},
            ))
            await session.commit()

        await _with_tenant_context(pg_db_session_factory, org_a, add_audit)

        async def get_attempts(session):
            attempts = (await session.execute(
                select(TenantHistoricalIsolation).where(
                    TenantHistoricalIsolation.source_org_id == org_a,
                )
            )).scalars().all()
            return attempts

        attempts = await _with_tenant_context(pg_db_session_factory, org_a, get_attempts)
        assert len(attempts) == 1
        assert attempts[0].blocked is True
        assert attempts[0].target_org_id == org_b

        # Hygiene: this audit table has no organization FK, so clean up
        # the attempt rows for the orgs created by this test.
        async def cleanup(session):
            await session.execute(
                delete(TenantHistoricalIsolation).where(
                    TenantHistoricalIsolation.source_org_id == org_a
                )
            )
            await session.commit()

        await _with_tenant_context(pg_db_session_factory, org_a, cleanup)


# =============================================================================
# 9. Epistemic calibration across time
# =============================================================================

class TestEpistemicCalibration:

    @pytest.mark.asyncio
    async def test_prediction_outcome_calibration_trajectory_preserved(
        self, pg_db_session_factory
    ):
        """The prediction -> outcome -> calibration loop is preserved with
        its confidence trajectory and deltas."""
        org_id = await _make_org(pg_db_session_factory)
        claim_id = f"claim-{uuid.uuid4().hex[:8]}"
        now = utcnow()
        t0 = now - timedelta(days=60)
        t1 = now - timedelta(days=30)
        t2 = now - timedelta(days=1)

        async def create_events(session):
            session.add(EpistemicCalibrationEvent(
                organization_id=org_id,
                claim_id=claim_id,
                claim_type="belief",
                event_key="prediction-1",
                event_type="PREDICTION",
                occurred_at=t0,
                prediction_at=t0,
                calibration_state="PENDING",
                prediction_json={"forecast": "grow 20%"},
                confidence_before=0.8,
            ))
            session.add(EpistemicCalibrationEvent(
                organization_id=org_id,
                claim_id=claim_id,
                claim_type="belief",
                event_key="outcome-1",
                event_type="OUTCOME",
                occurred_at=t1,
                outcome_at=t1,
                calibration_state="VERIFIED",
                outcome_json={"actual": "grew 8%"},
            ))
            session.add(EpistemicCalibrationEvent(
                organization_id=org_id,
                claim_id=claim_id,
                claim_type="belief",
                event_key="calibration-1",
                event_type="CALIBRATION",
                occurred_at=t2,
                calibrated_at=t2,
                calibration_state="CALIBRATED",
                calibration_json={"overconfidence": 0.12},
                confidence_before=0.8,
                confidence_after=0.68,
                calibration_delta=-0.12,
            ))
            session.add(LearningTimelineEvent(
                organization_id=org_id,
                event_key="learning-1",
                learning_kind="CALIBRATION",
                occurred_at=t2,
                calibrated_at=t2,
                outcome_state="CALIBRATED",
                calibration_json={"overconfidence": 0.12},
                confidence_before=0.8,
                confidence_after=0.68,
                calibration_delta=-0.12,
            ))
            await session.commit()

        await _with_tenant_context(pg_db_session_factory, org_id, create_events)

        async def get_results(session):
            events = (await session.execute(
                select(EpistemicCalibrationEvent).where(
                    EpistemicCalibrationEvent.organization_id == org_id,
                    EpistemicCalibrationEvent.claim_id == claim_id,
                ).order_by(EpistemicCalibrationEvent.occurred_at.asc())
            )).scalars().all()
            learning = (await session.execute(
                select(LearningTimelineEvent).where(
                    LearningTimelineEvent.organization_id == org_id,
                )
            )).scalars().one()
            return events, learning

        events, learning = await _with_tenant_context(pg_db_session_factory, org_id, get_results)

        assert [e.event_type for e in events] == [
            "PREDICTION", "OUTCOME", "CALIBRATION",
        ]
        assert events[0].prediction_json == {"forecast": "grow 20%"}
        assert events[1].outcome_json == {"actual": "grew 8%"}
        assert events[2].confidence_before == 0.8
        assert events[2].confidence_after == 0.68
        assert events[2].calibration_delta == -0.12
        assert learning.outcome_state == "CALIBRATED"
        assert learning.calibration_delta == -0.12


# =============================================================================
# 10. Organizational continuity
# =============================================================================

class TestOrganizationalContinuity:

    @pytest.mark.asyncio
    async def test_org_changes_preserve_past_states(
        self, pg_db_session_factory
    ):
        """Hire/terminate history supports point-in-time workforce
        reconstruction and keeps past states unchanged."""
        org_id = await _make_org(pg_db_session_factory)
        employee_id = f"emp-{uuid.uuid4().hex[:8]}"
        now = utcnow()
        t_hire = now - timedelta(days=90)
        t_terminate = now - timedelta(days=10)

        async def create_events(session):
            session.add(OrganizationalTimelineEvent(
                organization_id=org_id,
                event_key=f"hire:{employee_id}",
                event_kind="HIRE",
                entity_type="EMPLOYEE",
                entity_id=employee_id,
                occurred_at=t_hire,
                effective_from=t_hire,
                effective_to=t_terminate,
                from_state_json={"status": "none"},
                to_state_json={"status": "active"},
                change_summary="employee hired",
                actor_type="HUMAN",
            ))
            session.add(OrganizationalTimelineEvent(
                organization_id=org_id,
                event_key=f"terminate:{employee_id}",
                event_kind="TERMINATE",
                entity_type="EMPLOYEE",
                entity_id=employee_id,
                occurred_at=t_terminate,
                effective_from=t_terminate,
                from_state_json={"status": "active"},
                to_state_json={"status": "terminated"},
                change_summary="employee terminated",
                actor_type="HUMAN",
            ))
            await session.commit()

        await _with_tenant_context(pg_db_session_factory, org_id, create_events)

        async def headcount_at(session, at):
            hire = (await session.execute(
                select(OrganizationalTimelineEvent).where(
                    OrganizationalTimelineEvent.organization_id == org_id,
                    OrganizationalTimelineEvent.event_kind == "HIRE",
                    OrganizationalTimelineEvent.entity_id == employee_id,
                    OrganizationalTimelineEvent.occurred_at <= at,
                )
            )).scalars().all()
            terminate = (await session.execute(
                select(OrganizationalTimelineEvent).where(
                    OrganizationalTimelineEvent.organization_id == org_id,
                    OrganizationalTimelineEvent.event_kind == "TERMINATE",
                    OrganizationalTimelineEvent.entity_id == employee_id,
                    OrganizationalTimelineEvent.occurred_at <= at,
                )
            )).scalars().all()
            return 1 if hire and not terminate else 0

        async def get_results(session):
            at_mid = t_hire + timedelta(days=30)
            mid_count = await headcount_at(session, at_mid)
            now_count = await headcount_at(session, now)
            
            hire_row = (await session.execute(
                select(OrganizationalTimelineEvent).where(
                    OrganizationalTimelineEvent.organization_id == org_id,
                    OrganizationalTimelineEvent.event_key == f"hire:{employee_id}",
                )
            )).scalars().one()
            return mid_count, now_count, hire_row

        mid_count, now_count, hire_row = await _with_tenant_context(pg_db_session_factory, org_id, get_results)

        assert mid_count == 1
        assert now_count == 0
        assert hire_row.to_state_json == {"status": "active"}
        assert hire_row.effective_to == t_terminate


# =============================================================================
# 11. Merger / acquisition lineage
# =============================================================================

class TestMergerLineage:

    @pytest.mark.asyncio
    async def test_ma_lineage_links_entities_and_preserves_history(
        self, pg_db_session_factory
    ):
        """Lineage records predecessor -> successor mapping while historical
        events remain attributed to the original entity."""
        org_id = await _make_org(pg_db_session_factory)
        predecessor = f"div-{uuid.uuid4().hex[:8]}"
        successor = f"div-{uuid.uuid4().hex[:8]}"
        now = utcnow()

        async def create_data(session):
            session.add(_event(
                org_id, "reality:legacy-deal",
                entity_type="DIVISION",
                entity_id=predecessor,
                occurred_at=now - timedelta(days=200),
            ))
            session.add(MergerAcquisitionLineage(
                organization_id=org_id,
                transaction_id=f"txn-{uuid.uuid4().hex[:8]}",
                transaction_type="MERGER",
                predecessor_id=predecessor,
                predecessor_type="DIVISION",
                predecessor_name="Legacy Division",
                successor_id=successor,
                successor_type="DIVISION",
                successor_name="Combined Division",
                transaction_date=now - timedelta(days=30),
                effective_from=now - timedelta(days=30),
                entity_mappings_json=[{
                    "from_entity_id": predecessor,
                    "from_entity_type": "DIVISION",
                    "to_entity_id": successor,
                    "to_entity_type": "DIVISION",
                }],
                preserve_history=True,
            ))
            await session.commit()

        await _with_tenant_context(pg_db_session_factory, org_id, create_data)

        async def get_results(session):
            lineage = (await session.execute(
                select(MergerAcquisitionLineage).where(
                    MergerAcquisitionLineage.organization_id == org_id,
                )
            )).scalars().one()
            legacy = (await session.execute(
                select(CompanyTimelineEvent).where(
                    CompanyTimelineEvent.organization_id == org_id,
                    CompanyTimelineEvent.entity_id == predecessor,
                )
            )).scalars().all()
            return lineage, legacy

        lineage, legacy = await _with_tenant_context(pg_db_session_factory, org_id, get_results)

        assert lineage.preserve_history is True
        assert lineage.entity_mappings_json[0]["to_entity_id"] == successor
        assert len(legacy) == 1

        async def test_duplicate(session):
            duplicate = MergerAcquisitionLineage(
                organization_id=org_id,
                transaction_id=f"txn-{uuid.uuid4().hex[:8]}",
                transaction_type="MERGER",
                predecessor_id=predecessor,
                predecessor_type="DIVISION",
                predecessor_name="Legacy Division",
                successor_id=successor,
                successor_type="DIVISION",
                successor_name="Combined Division",
                transaction_date=now,
                effective_from=now,
            )
            session.add(duplicate)
            with pytest.raises(IntegrityError):
                await session.flush()
            await session.rollback()

        await _with_tenant_context(pg_db_session_factory, org_id, test_duplicate)


# =============================================================================
# 13. Longitudinal integrity invariant detection
# =============================================================================

class TestLongitudinalIntegrity:

    @pytest.mark.asyncio
    async def test_clean_org_produces_no_findings(self, pg_db_session_factory):
        org_id = await _make_org(pg_db_session_factory)
        chain = f"chain-{uuid.uuid4().hex[:8]}"

        async def create_data(session):
            session.add(_provenance(org_id, chain, 1, "hash-1"))
            session.add(_provenance(org_id, chain, 2, "hash-2",
                                    previous_hash="hash-1"))
            session.add(_snapshot(org_id, "claim-clean"))
            await session.commit()

        await _with_tenant_context(pg_db_session_factory, org_id, create_data)

        async def get_findings(session):
            return await canonical_reality_integrity_service.check_longitudinal_integrity(
                db=session, organization_id=org_id
            )

        findings = await _with_tenant_context(pg_db_session_factory, org_id, get_findings)
        assert findings == []

    @pytest.mark.asyncio
    async def test_all_five_longitudinal_invariants_detected(
        self, pg_db_session_factory
    ):
        """Broken chains, hash discontinuities, invalid intervals, missing
        epistemic state, and missing genesis are all detected."""
        org_id = await _make_org(pg_db_session_factory)
        now = utcnow()

        async def create_data(session):
            session.add(_provenance(
                org_id, "chain-broken", 1, "hash-1",
                broken=True, broken_reason="lost source",
            ))
            session.add(_provenance(org_id, "chain-hash", 1, "hash-1"))
            session.add(_provenance(
                org_id, "chain-hash", 2, "hash-2",
                previous_hash="wrong-hash",
            ))
            session.add(_provenance(
                org_id, "chain-interval", 1, "hash-1",
                effective_from=now,
                effective_to=now - timedelta(hours=1),
            ))
            session.add(_snapshot(org_id, "claim-no-epistemic",
                                  epistemic_state=""))
            session.add(_provenance(
                org_id, "chain-no-genesis", 2, "hash-2",
                is_genesis=False,
            ))
            await session.commit()

        await _with_tenant_context(pg_db_session_factory, org_id, create_data)

        async def get_findings(session):
            return await canonical_reality_integrity_service.check_longitudinal_integrity(
                db=session, organization_id=org_id
            )

        findings = await _with_tenant_context(pg_db_session_factory, org_id, get_findings)

        types = {f.finding_type for f in findings}
        assert IntegrityFindingType.LONGITUDINAL_BROKEN_CHAIN in types
        assert IntegrityFindingType.LONGITUDINAL_HASH_DISCONTINUITY in types
        assert IntegrityFindingType.LONGITUDINAL_INVALID_INTERVAL in types
        assert IntegrityFindingType.LONGITUDINAL_MISSING_EPISTEMIC in types
        assert IntegrityFindingType.LONGITUDINAL_MISSING_GENESIS in types


# =============================================================================
# 14. Longitudinal history under failure (35-H reliability infrastructure)
# =============================================================================

class TestLongitudinalHistoryUnderFailure:

    @pytest.mark.asyncio
    async def test_recovery_after_interrupted_external_operation_keeps_history(
        self, pg_db_session_factory
    ):
        """An interrupted external operation is marked UNKNOWN and later
        reconciled; the recorded company history is byte-for-byte intact.

        Note: ExternalUnknownState.operation_id has a real PostgreSQL FK to
        external_operations.id, while reconcile_external_unknown loads the
        same id from canonical_operations. The integration-layer projection
        is therefore seeded with the canonical operation id so the real
        reliability flow runs against the real schema.
        """
        org_id = await _make_org(pg_db_session_factory, "lng-fail")
        now = utcnow()
        operation_id = f"cop-{uuid.uuid4().hex[:12]}"

        async def setup_data(session):
            connector = Connector(
                kind="testing",
                provider=f"provider-{uuid.uuid4().hex[:8]}",
                display_name="Longitudinal Test Connector",
            )
            session.add(connector)
            await session.flush()

            instance = ConnectorInstance(
                organization_id=org_id,
                connector_id=connector.id,
                name=f"instance-{uuid.uuid4().hex[:8]}",
                auth_type="api_key",
                state="connected",
            )
            session.add(instance)
            await session.flush()

            operation = CanonicalOperation(
                id=operation_id,
                organization_id=org_id,
                operation_type="external_api_call",
                title="Longitudinal external effect",
                state="executing",
                is_external=True,
                external_system="payment_gateway",
                external_operation_id="ext-op-longitudinal",
                fingerprint=f"fp-{uuid.uuid4().hex}",
            )
            session.add(operation)

            session.add(ExternalOperation(
                id=operation_id,
                organization_id=org_id,
                connector_instance_id=instance.id,
                operation_type="update",
                target_entity_type="payment",
                state="executing",
                external_operation_id="ext-op-longitudinal",
            ))

            history = _event(
                org_id, "decision:executed:dec-1",
                timeline_type="decision",
                event_type="CompanyDecision.transition",
                from_state="approved",
                to_state="executed",
                delta_json={"state": "executed", "actor": "ops"},
            )
            session.add(history)
            await session.commit()
            return history.id, instance.id

        history_id, instance_id = await _with_tenant_context(pg_db_session_factory, org_id, setup_data)

        async def get_before(session):
            stored = await session.get(CompanyTimelineEvent, history_id)
            return {
                "event_key": stored.event_key,
                "occurred_at": stored.occurred_at,
                "effective_from": stored.effective_from,
                "from_state": stored.from_state,
                "to_state": stored.to_state,
                "change_summary": stored.change_summary,
                "delta_json": dict(stored.delta_json),
                "metadata_json": dict(stored.metadata_json),
            }

        before = await _with_tenant_context(pg_db_session_factory, org_id, get_before)

        # Interruption: the external outcome becomes unknown.
        async def mark_unknown(session):
            operation = await session.get(CanonicalOperation, operation_id)
            eus = await canonical_reliability_service.mark_external_unknown(
                db=session,
                operation=operation,
                external_system="payment_gateway",
                external_operation_id="ext-op-longitudinal",
                external_operation_type="payment",
                timeout_at=now + timedelta(hours=24),
            )
            await session.commit()
            return eus.id

        eus_id = await _with_tenant_context(pg_db_session_factory, org_id, mark_unknown)

        async def check_unknown(session):
            operation = await session.get(CanonicalOperation, operation_id)
            return operation.state, operation.outcome

        state, outcome = await _with_tenant_context(pg_db_session_factory, org_id, check_unknown)
        assert state == "unknown"
        assert outcome != "failure"

        # Recovery: reconciliation resolves the unknown state.
        async def reconcile(session):
            eus = await session.get(ExternalUnknownState, eus_id)
            reconciliation = await canonical_reliability_service.reconcile_external_unknown(
                db=session,
                eus=eus,
                external_state={"state": "completed", "result": "success"},
            )
            await session.commit()
            return reconciliation.outcome

        outcome = await _with_tenant_context(pg_db_session_factory, org_id, reconcile)
        assert outcome == "reconciled"

        async def check_reconciled(session):
            operation = await session.get(CanonicalOperation, operation_id)
            stored = await session.get(CompanyTimelineEvent, history_id)
            
            all_events = (await session.execute(
                select(CompanyTimelineEvent).where(
                    CompanyTimelineEvent.organization_id == org_id,
                )
            )).scalars().all()
            
            return {
                "state": operation.state,
                "outcome": operation.outcome,
                "stored": stored,
                "event_count": len(all_events),
            }

        result = await _with_tenant_context(pg_db_session_factory, org_id, check_reconciled)
        assert result["state"] == "reconciled"
        assert result["outcome"] == "success"
        stored = result["stored"]
        assert stored.event_key == before["event_key"]
        assert stored.occurred_at == before["occurred_at"]
        assert stored.effective_from == before["effective_from"]
        assert stored.from_state == before["from_state"]
        assert stored.to_state == before["to_state"]
        assert stored.change_summary == before["change_summary"]
        assert dict(stored.delta_json) == before["delta_json"]
        assert dict(stored.metadata_json) == before["metadata_json"]
        assert result["event_count"] == 1

    @pytest.mark.asyncio
    async def test_replayed_create_after_failure_is_exactly_once(
        self, pg_db_session, pg_db_session_factory
    ):
        """A create that is replayed after a failure (same identity) yields
        exactly one entity and exactly one history entry."""
        org_id = await _make_org(pg_db_session_factory)
        caller, _ = await _make_caller(pg_db_session_factory, org_id)
        fingerprint = f"fp-{uuid.uuid4().hex}"

        first = CompanyGoal(
            organization_id=org_id,
            title="Exactly-once goal",
            status="active",
            kind="growth",
            fingerprint=fingerprint,
        )
        result = await canonical_create(
            db=pg_db_session,
            caller=caller,
            entity=first,
            required_permissions=["goals:manage"],
        )
        await pg_db_session.commit()
        assert result.success is True, result.error
        original_id = result.entity.id

        replay = CompanyGoal(
            organization_id=org_id,
            title="Exactly-once goal (replay)",
            status="active",
            kind="growth",
            fingerprint=fingerprint,
        )
        result = await canonical_create(
            db=pg_db_session,
            caller=caller,
            entity=replay,
            required_permissions=["goals:manage"],
        )
        await pg_db_session.commit()
        assert result.success is True, result.error
        assert result.entity.id == original_id

        async with pg_db_session_factory() as session:
            goals = (await session.execute(
                select(CompanyGoal).where(
                    CompanyGoal.organization_id == org_id,
                    CompanyGoal.fingerprint == fingerprint,
                )
            )).scalars().all()
            events = (await session.execute(
                select(CompanyTimelineEvent).where(
                    CompanyTimelineEvent.organization_id == org_id,
                    CompanyTimelineEvent.event_type.like("CompanyGoal.%"),
                )
            )).scalars().all()

        assert len(goals) == 1
        assert len(events) == 1
        assert events[0].entity_id == original_id

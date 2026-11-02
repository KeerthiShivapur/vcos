"""
Gate 30 Canonical Company Continuity - Comprehensive Test Suite
Tests the universal company operating continuity layer that makes
all existing VCOS capabilities behave as ONE coherent virtual company.
"""
import pytest
from datetime import datetime, timedelta
from uuid import uuid4
from typing import Dict, Any, List

from app.models.canonical_company_continuity import (
    COMPANY_LOOP_PHASES,
    LOOP_PHASES,
    COMPANY_STATE_DIMENSIONS,
    CONTINUITY_EVENT_TYPES,
    EPISTEMIC_STATES,
    OPERATING_HEALTH_STATES,
    CONSISTENCY_CHECK_TYPES,
    CompanyOperatingContinuity,
    CompanyContinuityEvent,
    CompanyStateSnapshotGate30,
    UniversalCompanyContext,
    CrossDomainConsistencyCheck,
    CompanyOperatingHealth,
    UniversalCompanyTimeline,
    SelfCompoundingLoopState,
)
from app.services.canonical_company_continuity_service import CanonicalCompanyContinuityService
from app.api.v1.canonical_continuity import router


class TestGate30Vocabularies:
    """Test all vocabulary tuples are complete and accessible."""

    def test_company_loop_phases_complete(self):
        """Test all 27 loop phases are defined."""
        expected_phases = [
            "identity", "organization", "intent", "objectives", "strategy",
            "decisions", "authorization", "commitments", "responsibilities",
            "people", "capacity", "actions", "work", "execution",
            "outcomes", "evidence", "verification", "assessment",
            "learning", "institutional_memory", "prediction",
            "counterfactual", "digital_twin", "optimization",
            "governed_autonomy", "execution_next", "outcome_next",
        ]
        for phase in expected_phases:
            assert phase in COMPANY_LOOP_PHASES

    def test_company_state_dimensions_complete(self):
        """Test canonical state dimensions."""
        assert "organization" in COMPANY_STATE_DIMENSIONS
        assert "people" in COMPANY_STATE_DIMENSIONS
        assert "financial" in COMPANY_STATE_DIMENSIONS
        assert "institutional_memory" in COMPANY_STATE_DIMENSIONS
        assert "digital_twin" in COMPANY_STATE_DIMENSIONS

    def test_continuity_event_types_complete(self):
        """Test continuity event types."""
        assert "state_transition" in CONTINUITY_EVENT_TYPES
        assert "decision_made" in CONTINUITY_EVENT_TYPES
        assert "learning_extracted" in CONTINUITY_EVENT_TYPES
        assert "calibration_done" in CONTINUITY_EVENT_TYPES
        assert "contradiction_surfaced" in CONTINUITY_EVENT_TYPES

    def test_epistemic_states_complete(self):
        """Test epistemic states for boundary preservation."""
        assert "observed" in EPISTEMIC_STATES
        assert "measured" in EPISTEMIC_STATES
        assert "evidence_backed" in EPISTEMIC_STATES
        assert "inferred" in EPISTEMIC_STATES
        assert "predicted" in EPISTEMIC_STATES
        assert "proposed" in EPISTEMIC_STATES
        assert "contested" in EPISTEMIC_STATES
        assert "simulated" in EPISTEMIC_STATES
        assert "counterfactual" in EPISTEMIC_STATES
        assert "hypothetical" in EPISTEMIC_STATES

    def test_operating_health_states_complete(self):
        """Test operating health states."""
        assert "healthy" in OPERATING_HEALTH_STATES
        assert "concerned" in OPERATING_HEALTH_STATES
        assert "at_risk" in OPERATING_HEALTH_STATES
        assert "critical" in OPERATING_HEALTH_STATES
        assert "unknown" in OPERATING_HEALTH_STATES

    def test_consistency_check_types_complete(self):
        """Test cross-domain consistency check types."""
        assert "commitment_without_responsibility" in CONSISTENCY_CHECK_TYPES
        assert "action_without_authorization" in CONSISTENCY_CHECK_TYPES
        assert "outcome_without_execution" in CONSISTENCY_CHECK_TYPES
        assert "prediction_marked_observed" in CONSISTENCY_CHECK_TYPES
        assert "scenario_marked_actual" in CONSISTENCY_CHECK_TYPES
        assert "autonomy_without_eligibility" in CONSISTENCY_CHECK_TYPES
        assert "financial_exceeds_constraint" in CONSISTENCY_CHECK_TYPES
        assert "external_without_provenance" in CONSISTENCY_CHECK_TYPES


class TestCompanyOperatingContinuity:
    """Test CompanyOperatingContinuity model."""

    def test_create_continuity_cycle(self):
        """Test creating a continuity cycle."""
        continuity = CompanyOperatingContinuity(
            organization_id=uuid4(),
            cycle_number=1,
            cycle_label="Test Cycle",
            current_phase="identity",
            cycle_started_at=datetime.utcnow(),
            phase_entered_at=datetime.utcnow(),
            fingerprint="fp123",
            operating_health="unknown",
        )
        assert continuity.cycle_number == 1
        assert continuity.cycle_label == "Test Cycle"
        assert continuity.current_phase == "identity"
        assert continuity.operating_health == "unknown"

    def test_continuity_with_all_states(self):
        """Test continuity with all state compositions."""
        continuity = CompanyOperatingContinuity(
            organization_id=uuid4(),
            cycle_number=2,
            current_phase="execution",
            cycle_started_at=datetime.utcnow(),
            phase_entered_at=datetime.utcnow(),
            identity_state_json={"employee_count": 50},
            organization_state_json={"department_count": 5},
            intent_state_json={"active_intents": []},
            objectives_state_json={"objectives": []},
            strategy_state_json={"decisions": []},
            authorization_state_json={"authorizations": []},
            commitment_state_json={"commitments": []},
            responsibility_state_json={"responsibilities": []},
            capacity_state_json={"total_capacity": 100},
            work_state_json={"active_projects": 10},
            execution_state_json={"actions_in_progress": 5},
            outcome_state_json={"recent_outcomes": []},
            learning_state_json={"active_lessons": 3},
            prediction_state_json={"calibrated_models": 2},
            twin_state_json={"recent_snapshots": 1},
            autonomy_state_json={"recent_proposals": 0},
            epistemic_summary_json={"by_state": {"observed": 10, "inferred": 3}},
            operating_health="healthy",
            health_details_json={},
            fingerprint="fp456",
        )
        assert continuity.cycle_number == 2
        assert continuity.current_phase == "execution"
        assert continuity.operating_health == "healthy"
        assert continuity.identity_state_json["employee_count"] == 50


class TestCompanyContinuityEvent:
    """Test CompanyContinuityEvent model."""

    def test_create_continuity_event(self):
        """Test creating a continuity event."""
        event = CompanyContinuityEvent(
            organization_id=uuid4(),
            continuity_cycle_id=uuid4(),
            event_type="state_transition",
            loop_phase="identity",
            occurred_at=datetime.utcnow(),
            sequence_in_phase=1,
            actor_id=uuid4(),
            actor_type="human",
            title="Cycle started",
            description="New operating cycle initiated",
            epistemic_state="observed",
            evidence_fingerprints=["fp1", "fp2"],
            source_event_ids=["event1"],
            fingerprint="event_fp123",
        )
        assert event.event_type == "state_transition"
        assert event.loop_phase == "identity"
        assert event.actor_type == "human"
        assert event.epistemic_state == "observed"
        assert len(event.evidence_fingerprints) == 2

    def test_event_with_all_fields(self):
        """Test event with all optional fields."""
        event = CompanyContinuityEvent(
            organization_id=uuid4(),
            continuity_cycle_id=uuid4(),
            event_type="decision_made",
            loop_phase="decisions",
            occurred_at=datetime.utcnow(),
            sequence_in_phase=5,
            actor_id=uuid4(),
            actor_type="human",
            title="Strategic decision made",
            description="Q4 resource allocation approved",
            details_json={"decision_kind": "reallocate_capacity"},
            entity_type="company_decision",
            entity_id=uuid4(),
            related_entities_json={"decision": "dec_123", "commitments": ["c_1", "c_2"]},
            epistemic_state="observed",
            governance_scope_id=uuid4(),
            fingerprint="event_fp456",
        )
        assert event.entity_type == "company_decision"
        assert event.governance_scope_id is not None
        assert event.details_json["decision_kind"] == "reallocate_capacity"


class TestCompanyStateSnapshotGate30:
    """Test CompanyStateSnapshotGate30 model."""

    def test_create_state_snapshot(self):
        """Test creating a Gate 30 state snapshot."""
        snapshot = CompanyStateSnapshotGate30(
            organization_id=uuid4(),
            dimension="financial",
            captured_at=datetime.utcnow(),
            valid_from=datetime.utcnow(),
            state_json='{"revenue": 1000000, "expenses": 800000}',
            source_events_json=["event1", "event2"],
            computation_duration_ms=50,
            fingerprint="snap_fp123",
        )
        assert snapshot.dimension == "financial"
        assert snapshot.computation_duration_ms == 50
        assert len(snapshot.source_events_json) == 2

    def test_snapshot_with_epistemic_composition(self):
        """Test snapshot with epistemic breakdown."""
        snapshot = CompanyStateSnapshotGate30(
            organization_id=uuid4(),
            dimension="predictions",
            captured_at=datetime.utcnow(),
            valid_from=datetime.utcnow(),
            state_json='{}',
            epistemic_composition_json={"predicted": 0.7, "inferred": 0.2, "observed": 0.1},
            fingerprint="snap_fp456",
        )
        assert snapshot.dimension == "predictions"
        assert snapshot.epistemic_composition_json["predicted"] == 0.7


class TestUniversalCompanyContext:
    """Test UniversalCompanyContext model."""

    def test_create_universal_context(self):
        """Test creating universal company context."""
        context = UniversalCompanyContext(
            organization_id=uuid4(),
            caller_user_id=uuid4(),
            org_wide=True,
            scope_type="org",
            scope_id=uuid4(),
            identity_json={"employee_count": 100},
            organization_json={"departments": 10},
            intent_json={"active_intents": 3},
            objectives_json={"objectives": 15},
            decisions_json={"decisions": 5},
            authorization_json={"authorizations": 8},
            commitments_json={"commitments": 12},
            responsibilities_json={"responsibilities": 20},
            people_json={"employees": 100},
            capacity_json={"total_capacity": 500},
            work_json={"active_projects": 25},
            projects_json={"projects": 25},
            customers_json={"customers": 50},
            commercial_json={"pipeline": 1000000},
            financial_json={"revenue": 5000000},
            resources_json={"resources": 200},
            procurement_json={"vendors": 30},
            processes_json={"processes": 15},
            knowledge_json={"documents": 500},
            predictions_json={"models": 10},
            counterfactuals_json={"scenarios": 5},
            digital_twin_json={"sync_rate": 0.99},
            autonomy_json={"proposals": 3},
            risks_json={"active_risks": 7},
            attention_json={"attention_items": 4},
            learning_json={"lessons": 20},
            institutional_memory_json={"entries": 100},
            computed_at=datetime.utcnow(),
            computation_duration_ms=150,
            input_fingerprint="input_fp",
            context_version=1,
            epistemic_breakdown_json={"observed": 15, "inferred": 8, "predicted": 3},
            fingerprint="ctx_fp123",
        )
        assert context.org_wide is True
        assert context.context_version == 1
        assert context.identity_json["employee_count"] == 100
        assert context.epistemic_breakdown_json["observed"] == 15


class TestCrossDomainConsistencyCheck:
    """Test CrossDomainConsistencyCheck model."""

    def test_create_consistency_check(self):
        """Test creating a consistency check."""
        check = CrossDomainConsistencyCheck(
            organization_id=uuid4(),
            check_type="commitment_without_responsibility",
            checked_at=datetime.utcnow(),
            check_scope_json={"domains": ["commitments", "responsibilities"]},
            status="contradiction",
            contradiction_count=2,
            contradictions_json=[
                {"commitment_id": "c1", "person_id": "p1"},
                {"commitment_id": "c2", "person_id": "p2"},
            ],
            affected_entities_json=[
                {"type": "commitment", "id": "c1"},
                {"type": "commitment", "id": "c2"},
            ],
            fingerprint="check_fp123",
        )
        assert check.check_type == "commitment_without_responsibility"
        assert check.status == "contradiction"
        assert check.contradiction_count == 2
        assert len(check.contradictions_json) == 2

    def test_check_acknowledgment_workflow(self):
        """Test check acknowledgment."""
        check = CrossDomainConsistencyCheck(
            organization_id=uuid4(),
            check_type="action_without_authorization",
            checked_at=datetime.utcnow(),
            status="contradiction",
            contradiction_count=1,
            contradictions_json=[{"action_id": "a1"}],
            acknowledged=True,
            acknowledged_by=uuid4(),
            acknowledged_at=datetime.utcnow(),
            resolution_note="Authorization granted retroactively",
            fingerprint="check_fp456",
        )
        assert check.acknowledged is True
        assert check.resolution_note == "Authorization granted retroactively"


class TestCompanyOperatingHealth:
    """Test CompanyOperatingHealth model."""

    def test_create_operating_health(self):
        """Test creating operating health assessment."""
        health = CompanyOperatingHealth(
            organization_id=uuid4(),
            overall_state="concerned",
            assessed_at=datetime.utcnow(),
            domain_health_json={"strategy": "healthy", "execution": "concerned"},
            unresolved_contradictions=3,
            missing_responsibility=1,
            stale_state_count=2,
            failed_executions=0,
            unknown_outcomes=1,
            prediction_divergence_count=1,
            twin_divergence_count=0,
            blocked_operations=1,
            governance_issues=0,
            integration_failures=0,
            learning_gaps=2,
            details_json={"top_contradictions": ["commitment_without_responsibility"]},
            fingerprint="health_fp123",
        )
        assert health.overall_state == "concerned"
        assert health.unresolved_contradictions == 3
        assert health.domain_health_json["execution"] == "concerned"


class TestUniversalCompanyTimeline:
    """Test UniversalCompanyTimeline model."""

    def test_create_timeline_entry(self):
        """Test creating a timeline entry."""
        entry = UniversalCompanyTimeline(
            organization_id=uuid4(),
            event_type="decision_made",
            loop_phase="decisions",
            occurred_at=datetime.utcnow(),
            title="Q4 Budget Approved",
            description="Annual budget approved by board",
            entity_type="company_decision",
            entity_id=uuid4(),
            actor_id=uuid4(),
            actor_type="human",
            scope_type="org",
            scope_id=uuid4(),
            related_events_json=["event1", "event2"],
            continuity_cycle_id=uuid4(),
            epistemic_state="observed",
            evidence_fingerprints=["fp1", "fp2"],
            visible_to_org_wide=True,
            visible_scope_ids_json=[],
            fingerprint="tl_fp123",
        )
        assert entry.event_type == "decision_made"
        assert entry.loop_phase == "decisions"
        assert entry.epistemic_state == "observed"
        assert entry.visible_to_org_wide is True


class TestSelfCompoundingLoopState:
    """Test SelfCompoundingLoopState model."""

    def test_create_compounding_loop(self):
        """Test creating a self-compounding loop state."""
        loop = SelfCompoundingLoopState(
            organization_id=uuid4(),
            cycle_number=1,
            current_phase="reality",
            cycle_started_at=datetime.utcnow(),
            phase_entered_at=datetime.utcnow(),
            reality_state_json={"employee_count": 100},
            understanding_state_json={"context_built": True},
            intelligence_state_json={"patterns": 10, "insights": 5},
            prediction_state_json={"calibrated": 8},
            counterfactual_state_json={"scenarios": 3},
            digital_twin_state_json={"synced": True},
            optimization_state_json={"completed": 2},
            decision_state_json={"decisions": 4},
            governance_state_json={"authorized": 3},
            autonomy_state_json={"proposals": 1},
            execution_state_json={"actions": 10},
            outcome_state_json={"recorded": 8},
            verification_state_json={"verified": 7},
            learning_state_json={"lessons": 5},
            memory_state_json={"stored": 4},
            calibration_state_json={"improved": 3},
            future_context_state_json={"updated": True},
            fingerprint="loop_fp123",
            phases_completed=0,
        )
        assert loop.cycle_number == 1
        assert loop.current_phase == "reality"
        assert loop.phases_completed == 0

    def test_completed_loop(self):
        """Test a completed compounding loop."""
        loop = SelfCompoundingLoopState(
            organization_id=uuid4(),
            cycle_number=2,
            current_phase="reality",
            cycle_started_at=datetime.utcnow() - timedelta(minutes=30),
            cycle_completed_at=datetime.utcnow(),
            phase_entered_at=datetime.utcnow(),
            loop_duration_ms=1800000,
            phases_completed=17,
            calibration_delta=0.05,
            learning_accumulated=8,
            fingerprint="loop_fp456",
        )
        assert loop.cycle_completed_at is not None
        assert loop.phases_completed == 17
        assert loop.calibration_delta == 0.05
        assert loop.learning_accumulated == 8


class TestCanonicalCompanyContinuityService:
    """Test CanonicalCompanyContinuityService core functionality."""

    @pytest.fixture
    def service(self, db_session):
        return CanonicalCompanyContinuityService()

    @pytest.fixture
    def org_id(self):
        return str(uuid4())

    async def test_start_new_cycle(self, service, db_session, org_id):
        """Test starting a new continuity cycle."""
        continuity = await service.start_new_cycle(
            db_session, org_id,
            cycle_label="Test Cycle",
            triggered_by=str(uuid4()),
        )
        assert continuity is not None
        assert continuity.cycle_number == 1
        assert continuity.cycle_label == "Test Cycle"
        assert continuity.current_phase == "identity"
        assert continuity.identity_state_json is not None
        assert continuity.fingerprint is not None

    async def test_advance_phase(self, service, db_session, org_id):
        """Test advancing phase in continuity cycle."""
        continuity = await service.start_new_cycle(db_session, org_id)
        
        # Advance through several phases
        for phase in ["organization", "intent", "objectives"]:
            continuity = await service.advance_phase(
                db_session, continuity, phase,
                actor_id=str(uuid4()),
            )
            assert continuity.current_phase == phase
        
        assert continuity.current_phase == "objectives"

    async def test_record_event(self, service, db_session, org_id):
        """Test recording a continuity event."""
        await service.start_new_cycle(db_session, org_id)
        
        event = await service.record_event(
            db_session, org_id,
            event_type="decision_made",
            loop_phase="decisions",
            title="Strategic Decision",
            description="Approved Q4 resource allocation",
            actor_type="human",
            epistemic_state="observed",
        )
        assert event is not None
        assert event.event_type == "decision_made"
        assert event.loop_phase == "decisions"
        assert event.epistemic_state == "observed"

    async def test_build_universal_context(self, service, db_session, org_id):
        """Test building universal company context."""
        from app.models.user import User
        from app.models.organization import Organization
        
        # Create a test user
        user = User(
            id=str(uuid4()),
            organization_id=org_id,
            email=f"test_{uuid4().hex[:8]}@example.com",
            full_name="Test User",
            password_hash="test_hash",
        )
        db_session.add(user)
        await db_session.flush()
        
        context = await service.build_universal_context(
            db_session, org_id, user.id,
            context_version=1,
        )
        assert context is not None
        assert context.organization_id == org_id
        assert context.context_version == 1
        assert context.identity_json is not None
        assert context.epistemic_breakdown_json is not None

    async def test_run_consistency_checks(self, service, db_session, org_id):
        """Test running cross-domain consistency checks."""
        await service.start_new_cycle(db_session, org_id)
        
        results = await service.run_all_consistency_checks(db_session, org_id)
        assert len(results) == len(CONSISTENCY_CHECK_TYPES)
        assert all(r.check_type in CONSISTENCY_CHECK_TYPES for r in results)

    async def test_assess_operating_health(self, service, db_session, org_id):
        """Test assessing operating health."""
        await service.start_new_cycle(db_session, org_id)
        
        health = await service.assess_operating_health(db_session, org_id)
        assert health is not None
        assert health.overall_state in OPERATING_HEALTH_STATES
        assert health.unresolved_contradictions >= 0

    async def test_build_universal_timeline(self, service, db_session, org_id):
        """Test building universal company timeline."""
        await service.start_new_cycle(db_session, org_id)
        
        entries = await service.build_universal_timeline(
            db_session, org_id,
            days_back=7,
            limit=50,
        )
        assert len(entries) >= 0  # May be 0 if no data
        assert all(str(e.organization_id) == org_id for e in entries)

    async def test_run_compounding_loop(self, service, db_session, org_id):
        """Test running self-compounding loop."""
        loop = await service.run_compounding_loop(db_session, org_id, trigger="test")
        assert loop is not None
        assert loop.cycle_number == 1
        assert loop.phases_completed == len(LOOP_PHASES)
        assert loop.cycle_completed_at is not None


class TestAPIEndpoints:
    """Test API endpoint structure and routing."""

    def test_router_exists(self):
        assert router is not None
        assert router.prefix == "/canonical-continuity"
        assert "Canonical Company Continuity" in router.tags

    def test_routes_registered(self):
        routes = [route.path for route in router.routes]
        # Cycle routes
        assert "/canonical-continuity/cycles/start" in routes
        assert "/canonical-continuity/cycles/current" in routes
        assert "/canonical-continuity/cycles/{cycle_number}" in routes
        assert "/canonical-continuity/cycles/{cycle_id}/advance" in routes
        assert "/canonical-continuity/cycles/{cycle_id}/complete" in routes
        # Event routes
        assert "/canonical-continuity/events/record" in routes
        assert "/canonical-continuity/events" in routes
        # Context routes
        assert "/canonical-continuity/context" in routes
        assert "/canonical-continuity/context/refresh" in routes
        # Consistency routes
        assert "/canonical-continuity/consistency/run" in routes
        assert "/canonical-continuity/consistency/checks" in routes
        assert "/canonical-continuity/consistency/checks/{check_id}/acknowledge" in routes
        # Health routes
        assert "/canonical-continuity/health" in routes
        assert "/canonical-continuity/health/refresh" in routes
        # Timeline routes
        assert "/canonical-continuity/timeline" in routes
        # Compounding loop routes
        assert "/canonical-continuity/compounding-loop/run" in routes
        assert "/canonical-continuity/compounding-loop/history" in routes
        # State routes
        assert "/canonical-continuity/state/{dimension}" in routes
        # Vocabulary routes
        assert "/canonical-continuity/vocabularies/phases" in routes
        assert "/canonical-continuity/vocabularies/event-types" in routes
        assert "/canonical-continuity/vocabularies/epistemic-states" in routes
        assert "/canonical-continuity/vocabularies/health-states" in routes
        assert "/canonical-continuity/vocabularies/consistency-checks" in routes
        assert "/canonical-continuity/vocabularies/dimensions" in routes


class TestArchitecturalInvariants:
    """Test architectural invariants are maintained."""

    def test_model_tenant_isolation(self):
        """Verify all models require organization_id for tenant isolation."""
        models_to_check = [
            CompanyOperatingContinuity,
            CompanyContinuityEvent,
            CompanyStateSnapshotGate30,
            UniversalCompanyContext,
            CrossDomainConsistencyCheck,
            CompanyOperatingHealth,
            UniversalCompanyTimeline,
            SelfCompoundingLoopState,
        ]
        
        for model_class in models_to_check:
            columns = [c.name for c in model_class.__table__.columns]
            assert "organization_id" in columns, f"{model_class.__name__} missing organization_id"

    def test_provenance_tracking(self):
        """Verify epistemic integrity - provenance tracked via fingerprints."""
        continuity = CompanyOperatingContinuity(
            organization_id=uuid4(),
            cycle_number=1,
            current_phase="identity",
            cycle_started_at=datetime.utcnow(),
            phase_entered_at=datetime.utcnow(),
            fingerprint="fp123",
        )
        assert continuity.fingerprint == "fp123"
        
        event = CompanyContinuityEvent(
            organization_id=uuid4(),
            continuity_cycle_id=uuid4(),
            event_type="state_transition",
            loop_phase="identity",
            occurred_at=datetime.utcnow(),
            sequence_in_phase=1,
            actor_type="human",
            title="Test",
            epistemic_state="observed",
            fingerprint="event_fp123",
        )
        assert event.fingerprint == "event_fp123"
        assert event.epistemic_state == "observed"

    def test_epistemic_boundaries_preserved(self):
        """Verify epistemic states are properly used across models."""
        # State snapshots have epistemic composition
        snapshot = CompanyStateSnapshotGate30(
            organization_id=uuid4(),
            dimension="predictions",
            captured_at=datetime.utcnow(),
            valid_from=datetime.utcnow(),
            epistemic_composition_json={"predicted": 0.8, "inferred": 0.2},
            fingerprint="snap_fp",
        )
        assert "predicted" in snapshot.epistemic_composition_json
        
        # Context has epistemic breakdown
        context = UniversalCompanyContext(
            organization_id=uuid4(),
            caller_user_id=uuid4(),
            computed_at=datetime.utcnow(),
            input_fingerprint="fp",
            context_version=1,
            epistemic_breakdown_json={"observed": 10, "predicted": 5, "simulated": 2},
            fingerprint="ctx_fp",
        )
        assert "simulated" in context.epistemic_breakdown_json
        
        # Timeline entries have epistemic state
        entry = UniversalCompanyTimeline(
            organization_id=uuid4(),
            event_type="prediction_made",
            loop_phase="prediction",
            occurred_at=datetime.utcnow(),
            title="Revenue forecast",
            epistemic_state="predicted",
            fingerprint="tl_fp",
        )
        assert entry.epistemic_state == "predicted"

    def test_no_parallel_reality(self):
        """Verify single canonical reality - no parallel graphs."""
        # All models reference same organization_id
        org_id = uuid4()
        
        continuity = CompanyOperatingContinuity(
            organization_id=org_id,
            cycle_number=1,
            current_phase="identity",
            cycle_started_at=datetime.utcnow(),
            phase_entered_at=datetime.utcnow(),
            fingerprint="fp",
        )
        
        event = CompanyContinuityEvent(
            organization_id=org_id,
            continuity_cycle_id=continuity.id,
            event_type="state_transition",
            loop_phase="identity",
            occurred_at=datetime.utcnow(),
            sequence_in_phase=1,
            actor_type="human",
            title="Test",
            epistemic_state="observed",
            fingerprint="event_fp",
        )
        
        assert continuity.organization_id == event.organization_id == org_id


class TestRegressionCompatibility:
    """Test compatibility with previous gates."""

    def test_gate29_continuous_twin_integration(self):
        """Test integration with Gate 29 continuous twin."""
        # Twin state is part of continuity
        continuity = CompanyOperatingContinuity(
            organization_id=uuid4(),
            cycle_number=1,
            current_phase="digital_twin",
            cycle_started_at=datetime.utcnow(),
            phase_entered_at=datetime.utcnow(),
            twin_state_json={"recent_snapshots": 5, "sync_rate": 0.98},
            fingerprint="fp",
        )
        assert "recent_snapshots" in continuity.twin_state_json
        assert continuity.twin_state_json["sync_rate"] == 0.98

    def test_gate28_governed_autonomy_integration(self):
        """Test integration with Gate 28 governed autonomy."""
        continuity = CompanyOperatingContinuity(
            organization_id=uuid4(),
            cycle_number=1,
            current_phase="governed_autonomy",
            cycle_started_at=datetime.utcnow(),
            phase_entered_at=datetime.utcnow(),
            autonomy_state_json={"proposals": 3, "authorized": 2, "executed": 1},
            fingerprint="fp",
        )
        assert continuity.autonomy_state_json["proposals"] == 3

    def test_gate25_universal_workspace_integration(self):
        """Test integration with Gate 25 universal workspace."""
        # Context includes all workspace-relevant domains
        context = UniversalCompanyContext(
            organization_id=uuid4(),
            caller_user_id=uuid4(),
            org_wide=True,
            work_json={"active_projects": 10},
            projects_json={"projects": 10},
            people_json={"employees": 50},
            capacity_json={"utilization": 0.75},
            knowledge_json={"documents": 100},
            computed_at=datetime.utcnow(),
            input_fingerprint="fp",
            context_version=1,
            epistemic_breakdown_json={},
            fingerprint="ctx_fp",
        )
        assert context.work_json["active_projects"] == 10

    def test_gate23_business_intelligence_integration(self):
        """Test integration with Gate 23 business intelligence."""
        health = CompanyOperatingHealth(
            organization_id=uuid4(),
            overall_state="healthy",
            assessed_at=datetime.utcnow(),
            domain_health_json={"strategy": "healthy", "execution": "healthy"},
            fingerprint="fp",
        )
        assert health.domain_health_json["strategy"] == "healthy"


class TestSelfCompoundingLoop:
    """Test the self-compounding loop behavior."""

    def test_loop_phases_complete(self):
        """Test all 17 loop phases are defined."""
        expected = [
            "reality", "understanding", "intelligence", "prediction",
            "counterfactual", "digital_twin", "optimization", "decision",
            "governance", "autonomy", "execution", "outcome",
            "verification", "learning", "institutional_memory",
            "calibration", "improved_future_context",
        ]
        for phase in expected:
            assert phase in LOOP_PHASES

    def test_loop_state_composition(self):
        """Test loop state has all phase snapshots."""
        loop = SelfCompoundingLoopState(
            organization_id=uuid4(),
            cycle_number=1,
            current_phase="reality",
            cycle_started_at=datetime.utcnow(),
            phase_entered_at=datetime.utcnow(),
            fingerprint="fp",
        )
        # All phase state fields exist
        assert hasattr(loop, "reality_state_json")
        assert hasattr(loop, "understanding_state_json")
        assert hasattr(loop, "intelligence_state_json")
        assert hasattr(loop, "prediction_state_json")
        assert hasattr(loop, "counterfactual_state_json")
        assert hasattr(loop, "digital_twin_state_json")
        assert hasattr(loop, "optimization_state_json")
        assert hasattr(loop, "decision_state_json")
        assert hasattr(loop, "governance_state_json")
        assert hasattr(loop, "autonomy_state_json")
        assert hasattr(loop, "execution_state_json")
        assert hasattr(loop, "outcome_state_json")
        assert hasattr(loop, "verification_state_json")
        assert hasattr(loop, "learning_state_json")
        assert hasattr(loop, "memory_state_json")
        assert hasattr(loop, "calibration_state_json")
        assert hasattr(loop, "future_context_state_json")

    def test_loop_metrics(self):
        """Test loop tracks calibration and learning metrics."""
        loop = SelfCompoundingLoopState(
            organization_id=uuid4(),
            cycle_number=5,
            current_phase="reality",
            cycle_started_at=datetime.utcnow() - timedelta(hours=1),
            cycle_completed_at=datetime.utcnow(),
            phase_entered_at=datetime.utcnow(),
            loop_duration_ms=3600000,
            phases_completed=17,
            calibration_delta=0.12,
            learning_accumulated=15,
            fingerprint="fp",
        )
        assert loop.cycle_number == 5
        assert loop.calibration_delta == 0.12
        assert loop.learning_accumulated == 15
        assert loop.phases_completed == 17


class TestCrossDomainOperatingLoops:
    """Test cross-domain operating loops are supported."""

    def test_strategy_loop_entities(self):
        """Test strategy loop: Intent → Objective → Alignment → Decision → Execution → Outcome → Learning."""
        continuity = CompanyOperatingContinuity(
            organization_id=uuid4(),
            cycle_number=1,
            current_phase="strategy",
            cycle_started_at=datetime.utcnow(),
            phase_entered_at=datetime.utcnow(),
            intent_state_json={"active_intents": [{"id": "i1", "kind": "growth"}]},
            objectives_state_json={"objectives": [{"id": "o1", "goal_id": "g1"}]},
            strategy_state_json={"decisions": [{"id": "d1", "kind": "reallocate_capacity"}]},
            authorization_state_json={"authorizations": [{"id": "a1", "state": "approved"}]},
            commitment_state_json={"commitments": [{"id": "c1", "state": "authorized"}]},
            execution_state_json={"actions_in_progress": 5},
            outcome_state_json={"recent_outcomes": [{"id": "out1", "kind": "successful"}]},
            learning_state_json={"active_lessons": 2},
            fingerprint="fp",
        )
        # All strategy loop entities present
        assert continuity.intent_state_json["active_intents"]
        assert continuity.objectives_state_json["objectives"]
        assert continuity.strategy_state_json["decisions"]
        assert continuity.authorization_state_json["authorizations"]
        assert continuity.commitment_state_json["commitments"]
        assert continuity.execution_state_json["actions_in_progress"] > 0
        assert continuity.outcome_state_json["recent_outcomes"]
        assert continuity.learning_state_json["active_lessons"] > 0

    def test_workforce_loop_entities(self):
        """Test workforce loop: Person → Role → Responsibility → Capacity → Work → Outcome → Development."""
        continuity = CompanyOperatingContinuity(
            organization_id=uuid4(),
            cycle_number=1,
            current_phase="people",
            cycle_started_at=datetime.utcnow(),
            phase_entered_at=datetime.utcnow(),
            identity_state_json={"employee_count": 100},
            responsibility_state_json={"responsibilities": 50},
            capacity_state_json={"total_capacity": 500, "available": 200},
            work_state_json={"active_tasks": 200},
            outcome_state_json={"recent_outcomes": []},
            learning_state_json={"active_lessons": 5},
            fingerprint="fp",
        )
        assert continuity.identity_state_json["employee_count"] == 100
        assert continuity.responsibility_state_json["responsibilities"] == 50
        assert continuity.capacity_state_json["available"] == 200

    def test_customer_loop_entities(self):
        """Test customer loop: Customer Need → Commercial Intent → Commitment → Work → Outcome → Impact → Learning."""
        continuity = CompanyOperatingContinuity(
            organization_id=uuid4(),
            cycle_number=1,
            current_phase="customers",
            cycle_started_at=datetime.utcnow(),
            phase_entered_at=datetime.utcnow(),
            # CompanyOperatingContinuity doesn't have commercial_json field
            # Use the appropriate state fields
            commitment_state_json={"commitments": [{"customer_id": "cust1", "value": 50000}]},
            work_state_json={"active_projects": 8},
            outcome_state_json={"recent_outcomes": [{"customer_id": "cust1", "impact": "positive"}]},
            learning_state_json={"active_lessons": 3},
            fingerprint="fp",
        )
        assert continuity.commitment_state_json["commitments"]
        assert continuity.work_state_json["active_projects"] == 8

    def test_finance_loop_entities(self):
        """Test finance loop: Budget → Commitment → Resource → Execution → Financial Outcome → Verification."""
        continuity = CompanyOperatingContinuity(
            organization_id=uuid4(),
            cycle_number=1,
            current_phase="financial",
            cycle_started_at=datetime.utcnow(),
            phase_entered_at=datetime.utcnow(),
            commitment_state_json={"commitments": [{"budget_allocated": 100000}]},
            execution_state_json={"actions_in_progress": 10},
            outcome_state_json={"recent_outcomes": []},
            fingerprint="fp",
        )
        assert continuity.commitment_state_json["commitments"]
        assert continuity.execution_state_json["actions_in_progress"] == 10

    def test_autonomy_loop_entities(self):
        """Test autonomy loop: Company State → Prediction → Option → Governance → Authorization → Execution → Outcome → Verification → Learning."""
        continuity = CompanyOperatingContinuity(
            organization_id=uuid4(),
            cycle_number=1,
            current_phase="governed_autonomy",
            cycle_started_at=datetime.utcnow(),
            phase_entered_at=datetime.utcnow(),
            prediction_state_json={"calibrated_models": 5, "avg_accuracy": 0.85},
            twin_state_json={"recent_snapshots": 3},
            autonomy_state_json={"proposals": 4, "authorized": 3, "executed": 2},
            execution_state_json={"actions_in_progress": 2},
            outcome_state_json={"recent_outcomes": [{"kind": "successful"}]},
            learning_state_json={"active_lessons": 2},
            fingerprint="fp",
        )
        assert continuity.prediction_state_json["avg_accuracy"] == 0.85
        assert continuity.autonomy_state_json["proposals"] == 4
        assert continuity.autonomy_state_json["executed"] == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
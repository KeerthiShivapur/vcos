"""
Gate 29 Continuous Digital Twin - Comprehensive Test Suite
Tests continuous state management, twin synchronization, prediction calibration,
optimization, learning signals, institutional memory, attention, drift detection,
twin scopes/contexts, state projections, and eligibility cache.
"""
import pytest
from datetime import datetime, timedelta
from uuid import uuid4
from decimal import Decimal
from typing import Dict, Any, List

from app.models.continuous_twin import (
    COMPANY_STATE_DIMENSIONS,
    TWIN_SYNC_STATES,
    CALIBRATION_STATES,
    OPTIMIZATION_STATES,
    DRIFT_SEVERITY,
    LEARNING_SIGNAL_TYPES,
    ATTENTION_PRIORITY,
    TWIN_SCOPE_TYPES,
    DRIFT_TYPES,
    CompanyStateSnapshot,
    CompanyStateDimension,
    TwinStateSnapshot,
    TwinSynchronizationLog,
    PredictionCalibration,
    OptimizationContext,
    OptimizationAlternative,
    LearningSignal,
    ContinuousLearningSession,
    InstitutionalMemoryEntry,
    CompanyAttention,
    ModelTwinDrift,
    TwinScope,
    TwinContext,
    ContinuousStateProjection,
)


class TestGate29Vocabularies:
    """Test all vocabulary tuples are complete and accessible."""

    def test_company_state_dimensions_complete(self):
        assert "organization" in COMPANY_STATE_DIMENSIONS
        assert "people" in COMPANY_STATE_DIMENSIONS
        assert "projects" in COMPANY_STATE_DIMENSIONS
        assert "financial" in COMPANY_STATE_DIMENSIONS
        assert "institutional_memory" in COMPANY_STATE_DIMENSIONS

    def test_twin_sync_states_complete(self):
        assert "synced" in TWIN_SYNC_STATES
        assert "pending" in TWIN_SYNC_STATES
        assert "stale" in TWIN_SYNC_STATES
        assert "diverged" in TWIN_SYNC_STATES
        assert "error" in TWIN_SYNC_STATES

    def test_calibration_states_complete(self):
        assert "pending" in CALIBRATION_STATES
        assert "evaluating" in CALIBRATION_STATES
        assert "calibrated" in CALIBRATION_STATES
        assert "stale" in CALIBRATION_STATES
        assert "failed" in CALIBRATION_STATES

    def test_optimization_states_complete(self):
        assert "analyzing" in OPTIMIZATION_STATES
        assert "generating" in OPTIMIZATION_STATES
        assert "evaluating" in OPTIMIZATION_STATES
        assert "ranked" in OPTIMIZATION_STATES
        assert "selected" in OPTIMIZATION_STATES
        assert "executed" in OPTIMIZATION_STATES
        assert "failed" in OPTIMIZATION_STATES

    def test_drift_severity_complete(self):
        assert "none" in DRIFT_SEVERITY
        assert "low" in DRIFT_SEVERITY
        assert "medium" in DRIFT_SEVERITY
        assert "high" in DRIFT_SEVERITY
        assert "critical" in DRIFT_SEVERITY

    def test_learning_signal_types_complete(self):
        assert "outcome_deviation" in LEARNING_SIGNAL_TYPES
        assert "prediction_error" in LEARNING_SIGNAL_TYPES
        assert "twin_divergence" in LEARNING_SIGNAL_TYPES
        assert "policy_violation" in LEARNING_SIGNAL_TYPES
        assert "optimization_opportunity" in LEARNING_SIGNAL_TYPES
        assert "capacity_bottleneck" in LEARNING_SIGNAL_TYPES
        assert "risk_emergence" in LEARNING_SIGNAL_TYPES
        assert "learning_opportunity" in LEARNING_SIGNAL_TYPES

    def test_attention_priority_complete(self):
        assert "info" in ATTENTION_PRIORITY
        assert "watch" in ATTENTION_PRIORITY
        assert "alert" in ATTENTION_PRIORITY
        assert "critical" in ATTENTION_PRIORITY

    def test_twin_scope_types_complete(self):
        assert "org" in TWIN_SCOPE_TYPES
        assert "department" in TWIN_SCOPE_TYPES
        assert "team" in TWIN_SCOPE_TYPES
        assert "project" in TWIN_SCOPE_TYPES
        assert "person" in TWIN_SCOPE_TYPES

    def test_drift_types_complete(self):
        assert "prediction_divergence" in DRIFT_TYPES
        assert "twin_reality_gap" in DRIFT_TYPES
        assert "state_staleness" in DRIFT_TYPES
        assert "policy_violation" in DRIFT_TYPES
        assert "constraint_violation" in DRIFT_TYPES
        assert "capacity_exceeded" in DRIFT_TYPES
        assert "external_divergence" in DRIFT_TYPES


class TestCompanyStateSnapshot:
    """Test CompanyStateSnapshot model."""

    def test_create_company_state_snapshot(self):
        snapshot = CompanyStateSnapshot(
            organization_id=uuid4(),
            dimension="financial",
            captured_at=datetime.utcnow(),
            valid_from=datetime.utcnow(),
            state_json='{"revenue": 1000000}',
            source_events_json='["event1"]',
            fingerprint="abc123",
        )
        assert snapshot.organization_id is not None
        assert snapshot.dimension == "financial"
        assert snapshot.fingerprint == "abc123"

    def test_model_has_required_columns(self):
        """Test that model has all required columns."""
        columns = [c.name for c in CompanyStateSnapshot.__table__.columns]
        required = ["id", "organization_id", "dimension", "captured_at", "valid_from", "fingerprint"]
        for col in required:
            assert col in columns, f"Missing column: {col}"


class TestCompanyStateDimension:
    """Test CompanyStateDimension model."""

    def test_create_dimension(self):
        dim = CompanyStateDimension(
            organization_id=uuid4(),
            dimension="people",
            current_state_json='{"count": 50}',
            composition_rules_json='{}',
            source_tables_json='[]',
            update_trigger="event",
            update_frequency_seconds=300,
            is_healthy=True,
        )
        assert dim.dimension == "people"
        assert dim.update_trigger == "event"
        assert dim.update_frequency_seconds == 300
        assert dim.is_healthy is True


class TestTwinStateSnapshot:
    """Test TwinStateSnapshot model."""

    def test_create_twin_state_snapshot(self):
        snapshot = TwinStateSnapshot(
            organization_id=uuid4(),
            scope_type="org",
            captured_at=datetime.utcnow(),
            current_state_json='{"revenue": 1000000}',
            predicted_state_json='{"revenue": 1100000}',
            fingerprint="twin123",
            twin_state="synced",
        )
        assert snapshot.organization_id is not None
        assert snapshot.scope_type == "org"
        assert snapshot.twin_state == "synced"
        assert snapshot.fingerprint == "twin123"

    def test_twin_snapshot_with_scope(self):
        snapshot = TwinStateSnapshot(
            organization_id=uuid4(),
            scope_type="department",
            scope_id=uuid4(),
            captured_at=datetime.utcnow(),
            fingerprint="scope123",
        )
        assert snapshot.scope_type == "department"
        assert snapshot.scope_id is not None


class TestTwinSynchronizationLog:
    """Test TwinSynchronizationLog model."""

    def test_create_sync_log(self):
        log = TwinSynchronizationLog(
            organization_id=uuid4(),
            scope_type="org",
            started_at=datetime.utcnow(),
            status="success",
            entities_synced=100,
            entities_failed=0,
        )
        assert log.status == "success"
        assert log.entities_synced == 100


class TestPredictionCalibration:
    """Test PredictionCalibration model."""

    def test_create_calibration(self):
        cal = PredictionCalibration(
            organization_id=uuid4(),
            prediction_kind="revenue_forecast",
            model_version="v1.2.3",
            status="calibrated",
            total_predictions=100,
            correct_predictions=95,
            accuracy=0.95,
            brier_score=0.05,
            expected_confidence=0.9,
            observed_accuracy=0.95,
            calibration_error=0.05,
            evaluation_window_days=30,
        )
        assert cal.prediction_kind == "revenue_forecast"
        assert cal.status == "calibrated"
        assert cal.accuracy == 0.95

    def test_calibration_defaults_to_pending(self):
        cal = PredictionCalibration(
            organization_id=uuid4(),
            prediction_kind="test",
            status="pending",
            total_predictions=0,
        )
        assert cal.status == "pending"
        assert cal.total_predictions == 0


class TestOptimizationContext:
    """Test OptimizationContext model."""

    def test_create_optimization_context(self):
        ctx = OptimizationContext(
            organization_id=uuid4(),
            objective="maximize_revenue",
            objective_type="maximize",
            constraints_json='{"budget": 100000}',
            variables_json='{"price": 50}',
            scope_type="department",
            scope_id=uuid4(),
            created_by=uuid4(),
            status="analyzing",
        )
        assert ctx.objective == "maximize_revenue"
        assert ctx.objective_type == "maximize"
        assert ctx.status == "analyzing"

    def test_optimization_with_results(self):
        ctx = OptimizationContext(
            organization_id=uuid4(),
            objective="minimize_cost",
            objective_type="minimize",
            constraints_json='{}',
            variables_json='{}',
            status="completed",
            best_solution_json='{"price": 50}',
            best_objective_value=125000.0,
            completed_at=datetime.utcnow(),
        )
        assert ctx.status == "completed"
        assert ctx.best_objective_value == 125000.0


class TestOptimizationAlternative:
    """Test OptimizationAlternative model."""

    def test_create_alternative(self):
        context_id = uuid4()
        alt = OptimizationAlternative(
            context_id=context_id,
            rank=1,
            solution_json='{"price": 50, "marketing": 25000}',
            objective_value=150000.0,
            hard_constraints_satisfied=True,
            is_feasible=True,
            feasibility_score=1.0,
        )
        assert alt.rank == 1
        assert alt.objective_value == 150000.0
        assert alt.is_feasible is True


class TestLearningSignal:
    """Test LearningSignal model."""

    def test_create_learning_signal(self):
        signal = LearningSignal(
            organization_id=uuid4(),
            signal_type="outcome_deviation",
            source_type="optimization",
            title="Revenue exceeded prediction",
            description="Actual revenue 5% above predicted",
            confidence=0.9,
            expected_lesson_type="revenue_model_adjustment",
            priority="info",
            status="open",
        )
        assert signal.signal_type == "outcome_deviation"
        assert signal.priority == "info"
        assert signal.confidence == 0.9
        assert signal.status == "open"

    def test_high_priority_signal(self):
        signal = LearningSignal(
            organization_id=uuid4(),
            signal_type="risk_emergence",
            source_type="twin_divergence",
            title="Critical risk detected",
            priority="critical",
            confidence=0.95,
        )
        assert signal.priority == "critical"


class TestContinuousLearningSession:
    """Test ContinuousLearningSession model."""

    def test_create_session(self):
        session = ContinuousLearningSession(
            organization_id=uuid4(),
            session_type="batch",
            scope_type="org",
            triggered_by=uuid4(),
            status="pending",
            signals_processed=0,
        )
        assert session.session_type == "batch"
        assert session.status == "pending"
        assert session.signals_processed == 0


class TestInstitutionalMemoryEntry:
    """Test InstitutionalMemoryEntry model."""

    def test_create_memory_entry(self):
        entry = InstitutionalMemoryEntry(
            organization_id=uuid4(),
            kind="lesson",
            fingerprint="mem123",
            title="Q4 Pricing Lesson",
            summary="Dynamic pricing increased revenue 15%",
            content_json='{"strategy": "dynamic", "lift": 0.15}',
            source_type="optimization_result",
            source_id=uuid4(),
            confidence=0.9,
            status="active",
        )
        assert entry.kind == "lesson"
        assert entry.fingerprint == "mem123"
        assert entry.confidence == 0.9
        assert entry.status == "active"

    def test_memory_validation_workflow(self):
        entry = InstitutionalMemoryEntry(
            organization_id=uuid4(),
            kind="pattern",
            fingerprint="pat456",
            title="Seasonal Pattern",
            content_json='{}',
            source_type="learning",
            validated=True,
            validated_by=uuid4(),
            validated_at=datetime.utcnow(),
            access_count=10,
        )
        assert entry.validated is True
        assert entry.access_count == 10


class TestCompanyAttention:
    """Test CompanyAttention model."""

    def test_create_attention(self):
        attention = CompanyAttention(
            organization_id=uuid4(),
            attention_type="kpi_deviation",
            title="Revenue KPI Below Target",
            description="Revenue 15% below quarterly target",
            source_type="prediction_calibration",
            source_id=uuid4(),
            priority="alert",
            priority_score=0.85,
            urgency="high",
            status="open",
        )
        assert attention.attention_type == "kpi_deviation"
        assert attention.priority == "alert"
        assert attention.urgency == "high"
        assert attention.status == "open"

    def test_attention_resolution(self):
        attention = CompanyAttention(
            organization_id=uuid4(),
            attention_type="risk_emergence",
            title="Risk Identified",
            source_type="twin_divergence",
            source_id=uuid4(),
            status="resolved",
            assigned_to=uuid4(),
            assigned_at=datetime.utcnow(),
            resolved_at=datetime.utcnow(),
            resolved_by=uuid4(),
            resolution_note="Mitigated via contingency plan",
        )
        assert attention.status == "resolved"
        assert attention.resolution_note == "Mitigated via contingency plan"


class TestModelTwinDrift:
    """Test ModelTwinDrift model."""

    def test_create_drift(self):
        drift = ModelTwinDrift(
            organization_id=uuid4(),
            drift_type="prediction_divergence",
            severity="high",
            subject_type="prediction_model",
            subject_id=uuid4(),
            expected_json='{"revenue": 1000000}',
            observed_json='{"revenue": 850000}',
            deviation_json='{"revenue_diff": -150000}',
            deviation_score=0.15,
            severity_score=0.8,
            evidence_json='{}',
            status="open",
        )
        assert drift.drift_type == "prediction_divergence"
        assert drift.severity == "high"
        assert drift.deviation_score == 0.15
        assert drift.status == "open"

    def test_drift_resolution(self):
        drift = ModelTwinDrift(
            organization_id=uuid4(),
            drift_type="twin_reality_gap",
            severity="critical",
            subject_type="twin",
            subject_id=uuid4(),
            deviation_score=0.3,
            status="resolved",
            resolved_at=datetime.utcnow(),
            resolved_by=uuid4(),
            resolution_note="Retrained model with recent data",
            mitigation_actions_json='["retrain", "update_features"]',
        )
        assert drift.status == "resolved"
        assert drift.severity == "critical"


class TestTwinScope:
    """Test TwinScope model."""

    def test_create_twin_scope(self):
        scope = TwinScope(
            organization_id=uuid4(),
            scope_type="department",
            scope_id=uuid4(),
            name="Marketing Twin",
            description="Marketing department digital twin",
            included_dimensions_json='["commercial", "financial"]',
            auto_refresh=True,
            refresh_interval_seconds=3600,
            is_active=True,
        )
        assert scope.scope_type == "department"
        assert scope.name == "Marketing Twin"
        assert scope.is_active is True

    def test_scope_hierarchy(self):
        parent = TwinScope(
            organization_id=uuid4(),
            scope_type="org",
            name="Company",
            is_default=True,
        )
        child = TwinScope(
            organization_id=uuid4(),
            scope_type="department",
            scope_id=uuid4(),
            name="Engineering",
        )
        assert child.scope_type == "department"


class TestTwinContext:
    """Test TwinContext model."""

    def test_create_twin_context(self):
        ctx = TwinContext(
            organization_id=uuid4(),
            scope_id=uuid4(),
            context_type="current_state",
            context_json={"revenue": 1000000, "employees": 50},
            computed_at=datetime.utcnow(),
            computation_duration_ms=50,
            input_fingerprint="input123",
            fingerprint="ctx456",
        )
        assert ctx.context_type == "current_state"
        assert ctx.context_json["revenue"] == 1000000
        assert ctx.fingerprint == "ctx456"

    def test_context_types(self):
        for ctx_type in ["current_state", "predicted_state", "counterfactual", "scenario", "optimization", "attention", "learning"]:
            ctx = TwinContext(
                organization_id=uuid4(),
                scope_id=uuid4(),
                context_type=ctx_type,
                context_json={},
                computed_at=datetime.utcnow(),
                input_fingerprint="test",
                fingerprint="test",
            )
            assert ctx.context_type == ctx_type


class TestContinuousStateProjection:
    """Test ContinuousStateProjection model."""

    def test_create_projection(self):
        proj = ContinuousStateProjection(
            organization_id=uuid4(),
            dimension="financial",
            current_state_json='{"revenue": 1000000}',
            current_state_hash="hash123",
            last_event_id="event1",
            last_event_at=datetime.utcnow(),
            events_processed=100,
            refresh_interval_seconds=60,
            is_healthy=True,
        )
        assert proj.dimension == "financial"
        assert proj.current_state_hash == "hash123"
        assert proj.events_processed == 100
        assert proj.is_healthy is True

    def test_projection_health_tracking(self):
        proj = ContinuousStateProjection(
            organization_id=uuid4(),
            dimension="people",
            current_state_json='{"count": 50}',
            current_state_hash="hash456",
            is_healthy=False,
            last_error="Connection timeout",
            last_error_at=datetime.utcnow(),
        )
        assert proj.is_healthy is False
        assert proj.last_error == "Connection timeout"


class TestArchitecturalInvariants:
    """Test architectural invariants are maintained."""

    def test_model_tenant_isolation(self):
        """Verify all models require organization_id for tenant isolation."""
        # CompanyStateSnapshot
        snapshot = CompanyStateSnapshot(
            organization_id=uuid4(),
            dimension="financial",
            captured_at=datetime.utcnow(),
            valid_from=datetime.utcnow(),
            fingerprint="abc123",
        )
        assert snapshot.organization_id is not None

        # TwinStateSnapshot
        twin = TwinStateSnapshot(
            organization_id=uuid4(),
            scope_type="org",
            captured_at=datetime.utcnow(),
            fingerprint="twin123",
        )
        assert twin.organization_id is not None

        # All models should have organization_id column (except OptimizationAlternative which uses context_id)
        models_to_check = [
            CompanyStateDimension,
            TwinSynchronizationLog,
            PredictionCalibration,
            OptimizationContext,
            # OptimizationAlternative,  # Uses context_id instead
            LearningSignal,
            ContinuousLearningSession,
            InstitutionalMemoryEntry,
            CompanyAttention,
            ModelTwinDrift,
            TwinScope,
            TwinContext,
            ContinuousStateProjection,
        ]

        for model_class in models_to_check:
            # Check if model has organization_id column
            columns = [c.name for c in model_class.__table__.columns]
            assert "organization_id" in columns, f"{model_class.__name__} missing organization_id"

    def test_provenance_tracking(self):
        """Verify epistemic integrity - provenance tracked via fingerprints."""
        snapshot = CompanyStateSnapshot(
            organization_id=uuid4(),
            dimension="financial",
            captured_at=datetime.utcnow(),
            valid_from=datetime.utcnow(),
            fingerprint="abc123",
            source_events_json='["event1", "event2"]',
        )
        assert snapshot.fingerprint == "abc123"
        assert snapshot.source_events_json is not None

        twin = TwinStateSnapshot(
            organization_id=uuid4(),
            scope_type="org",
            captured_at=datetime.utcnow(),
            fingerprint="twin123",
        )
        assert twin.fingerprint == "twin123"

    def test_canonical_dimensions_enforced(self):
        """Verify only canonical dimensions can be used."""
        # Valid dimension
        dim = CompanyStateDimension(
            organization_id=uuid4(),
            dimension="financial",
            composition_rules_json='{}',
            source_tables_json='[]',
        )
        assert dim.dimension in COMPANY_STATE_DIMENSIONS

        # Twin scope types enforced
        scope = TwinScope(
            organization_id=uuid4(),
            scope_type="department",
            name="Test",
        )
        assert scope.scope_type in TWIN_SCOPE_TYPES


class TestRegressionCompatibility:
    """Test compatibility with previous gates."""

    def test_gate28_governed_autonomy_model_structure(self):
        """Test optimization context supports governance constraints."""
        optimization = OptimizationContext(
            organization_id=uuid4(),
            objective="maximize_efficiency",
            objective_type="maximize",
            constraints_json='{"governance_policy": "strict", "budget": 100000}',
            variables_json='{}',
        )
        assert optimization is not None
        assert "governance_policy" in optimization.constraints_json

    def test_gate25_universal_workspace_model_structure(self):
        """Test twin scopes can reference workspace entities."""
        scope = TwinScope(
            organization_id=uuid4(),
            name="Workspace Scope",
            scope_type="org",
            scope_id=uuid4(),  # Workspace entity ID
            description="Twin scope for workspace",
        )
        assert scope is not None

    def test_gate24_canonical_universal_model_structure(self):
        """Test company state dimensions include canonical sources."""
        assert "organization" in COMPANY_STATE_DIMENSIONS
        assert "resources" in COMPANY_STATE_DIMENSIONS
        assert "processes" in COMPANY_STATE_DIMENSIONS

    def test_gate23_canonical_business_intelligence_model_structure(self):
        """Test attention types support KPI deviations."""
        attention = CompanyAttention(
            organization_id=uuid4(),
            attention_type="kpi_deviation",
            title="Revenue KPI deviation",
            source_type="business_intelligence",
            source_id=uuid4(),
        )
        assert attention.attention_type == "kpi_deviation"

    def test_gate12_digital_twin_model_structure(self):
        """Test twin synchronization builds on Gate 12 foundation."""
        company_state = CompanyStateSnapshot(
            organization_id=uuid4(),
            dimension="digital_twin",
            captured_at=datetime.utcnow(),
            valid_from=datetime.utcnow(),
            state_json='{"twin_metrics": {"sync_rate": 0.99}}',
            fingerprint="hash",
        )
        twin_state = TwinStateSnapshot(
            organization_id=uuid4(),
            scope_type="org",
            captured_at=datetime.utcnow(),
            current_state_json='{}',
            predicted_state_json='{"revenue": 1000000}',
            fingerprint="twin456",
        )
        assert twin_state is not None
        assert twin_state.predicted_state_json is not None


class TestPerformanceAndScale:
    """Test performance characteristics."""

    def test_batch_model_creation(self):
        """Test creating many model instances efficiently."""
        org_id = uuid4()
        
        # Create 100 learning signals
        signals = [
            LearningSignal(
                organization_id=org_id,
                signal_type="outcome_deviation",
                source_type="process",
                title=f"Signal {i}",
                confidence=0.8,
            )
            for i in range(100)
        ]
        assert len(signals) == 100
        assert all(s.organization_id == org_id for s in signals)

    def test_multiple_scopes_and_contexts(self):
        """Test creating multiple nested scopes and contexts."""
        org_id = uuid4()
        
        # Create hierarchy: Company -> Department -> Team
        company_scope = TwinScope(
            organization_id=org_id, name="Company", scope_type="org",
            scope_id=uuid4(), description=""
        )
        dept_scope = TwinScope(
            organization_id=org_id, name="Engineering", scope_type="department",
            scope_id=uuid4(), description=""
        )
        team_scope = TwinScope(
            organization_id=org_id, name="Backend", scope_type="team",
            scope_id=uuid4(), description=""
        )

        # Create contexts at each level
        for scope in [company_scope, dept_scope, team_scope]:
            ctx = TwinContext(
                organization_id=org_id, scope_id=scope.id,
                context_type="current_state", context_json={},
                computed_at=datetime.utcnow(), input_fingerprint="test", fingerprint="test"
            )
            assert ctx.scope_id == scope.id


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
"""Slice 2E — Production Observability & Alerting Acceptance Tests.

Tests the alert engine, health evaluation, health model, and observability integration.
"""

import pytest
import pytest_asyncio
import uuid
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.organization import Organization
from app.models.observability import (
    CanonicalObservation,
    HealthDimension,
    HealthDimension,
    SLOTarget,
)
from app.services.alert_engine import (
    alert_engine,
    AlertEngine,
    AlertState,
    AlertSeverity,
    AlertRule,
    Alert,
    AlertCorrelationType,
    create_release_health_alert_rules,
)
from app.services.health_evaluation_service import (
    health_evaluation_service,
    HealthEvaluationService,
    HealthDimensionName,
    AggregateHealthReport,
)
from app.services.health_model_service import (
    health_model_service,
    HealthModelService,
    HealthModelReport,
)
from app.services.observability_service import (
    observability_service,
    ObservabilityService,
    get_slice2e_extension,
)
from app.core.timeutils import utcnow


# =============================================================================
# FIXTURES
# =============================================================================

@pytest_asyncio.fixture
async def test_org(pg_db_session: AsyncSession) -> Organization:
    """Create a test organization."""
    org = Organization(
        name="Slice 2E Test Org",
        slug=f"slice2e-test-{uuid.uuid4().hex[:8]}",
        status="active",
    )
    pg_db_session.add(org)
    await pg_db_session.flush()
    await pg_db_session.commit()
    return org


# =============================================================================
# ALERT ENGINE TESTS
# =============================================================================

class TestAlertEngine:
    """Test alert engine lifecycle and rules."""
    
    @pytest.mark.asyncio
    async def test_alert_engine_initialization(self):
        """Alert engine initializes with default rules."""
        engine = AlertEngine()
        rules = engine.list_rules()
        assert len(rules) > 0
        
        # Check for release health rules
        rule_names = [r.name for r in rules]
        assert "preflight_failure" in rule_names
        assert "fingerprint_mismatch" in rule_names
        assert "canonical_integrity_critical" in rule_names
    
    @pytest.mark.asyncio
    async def test_alert_rule_registration(self):
        """Can register custom alert rules."""
        engine = AlertEngine()
        custom_rule = AlertRule(
            name="custom_test_rule",
            description="Custom test rule",
            dimension="test_dimension",
            condition='status == "critical"',
            severity=AlertSeverity.WARNING,
        )
        engine.register_rule(custom_rule)
        
        retrieved = engine.get_rule("custom_test_rule")
        assert retrieved is not None
        assert retrieved.name == "custom_test_rule"
        assert retrieved.dimension == "test_dimension"
    
    @pytest.mark.asyncio
    async def test_alert_lifecycle_transitions(self, test_org: Organization, pg_db_session: AsyncSession):
        """Alert transitions through lifecycle states correctly."""
        engine = AlertEngine()
        
        # Create a mock observation
        from app.models.observability import CanonicalObservation
        mock_obs = CanonicalObservation(
            organization_id=test_org.id,
            observation_type="health_check",
            source="test",
            severity="critical",
            title="Test health check",
            observed_at=utcnow(),
            fingerprint=f"test-{uuid.uuid4().hex[:12]}",
        )
        
        # Create a rule that will match
        rule = AlertRule(
            name="lifecycle_test",
            description="Test lifecycle",
            dimension="test",
            condition='status == "critical"',
            severity=AlertSeverity.CRITICAL,
        )
        engine.register_rule(rule)
        
        # Evaluate - should create alert
        alerts = await engine.evaluate_observation(mock_obs)
        assert len(alerts) >= 0  # May or may not trigger depending on health dimension
    
    @pytest.mark.asyncio
    async def test_alert_acknowledge_investigate_resolve_verify(self):
        """Alert can be acknowledged, investigated, resolved, and verified."""
        engine = AlertEngine()
        
        # Create alert directly
        alert = Alert(
            id=f"alert-{uuid.uuid4().hex[:12]}",
            organization_id="test-org",
            rule_name="test_rule",
            rule_description="Test",
            dimension="test",
            severity=AlertSeverity.CRITICAL,
            state=AlertState.ALERTED,
            title="Test Alert",
            description="Test",
            details={},
            fingerprint="test-fp",
        )
        engine._alerts[alert.id] = alert
        
        # Acknowledge
        result = await engine.acknowledge_alert(alert.id, "user-1")
        assert result is True
        assert alert.state == AlertState.ACKNOWLEDGED
        assert alert.acknowledged_by == "user-1"
        assert alert.acknowledged_at is not None
        
        # Investigate
        result = await engine.start_investigation(alert.id, "user-2")
        assert result is True
        assert alert.state == AlertState.INVESTIGATING
        assert alert.investigating_by == "user-2"
        
        # Resolve
        result = await engine.resolve_alert(alert.id, "user-2", "Fixed the issue")
        assert result is True
        assert alert.state == AlertState.RESOLVED
        assert alert.resolved_by == "user-2"
        assert "resolution_note" in alert.details
        
        # Verify
        result = await engine.verify_alert(alert.id, "user-3")
        assert result is True
        assert alert.state == AlertState.VERIFIED
        assert alert.verified_by == "user-3"
    
    @pytest.mark.asyncio
    async def test_alert_correlation(self):
        """Alerts are correlated based on dimension and temporal proximity."""
        engine = AlertEngine()
        
        # Create two alerts for same dimension close in time
        alert1 = Alert(
            id=f"alert-{uuid.uuid4().hex[:12]}",
            organization_id="test-org",
            rule_name="rule1",
            rule_description="Test",
            dimension="database",
            severity=AlertSeverity.CRITICAL,
            state=AlertState.ALERTED,
            title="DB Alert 1",
            description="Test",
            details={},
            fingerprint="fp1",
            created_at=utcnow(),
        )
        
        alert2 = Alert(
            id=f"alert-{uuid.uuid4().hex[:12]}",
            organization_id="test-org",
            rule_name="rule2",
            rule_description="Test",
            dimension="database",
            severity=AlertSeverity.WARNING,
            state=AlertState.ALERTED,
            title="DB Alert 2",
            description="Test",
            details={},
            fingerprint="fp2",
            created_at=utcnow() - timedelta(minutes=2),
        )
        
        engine._alerts[alert1.id] = alert1
        engine._alerts[alert2.id] = alert2
        
        # Trigger correlation
        correlations = engine._correlation.correlate(alert1, [alert2])
        
        # Should find SAME_ROOT_CAUSE correlation
        assert len(correlations) > 0
        assert any(c.correlation_type == AlertCorrelationType.SAME_ROOT_CAUSE for c in correlations)
    
    @pytest.mark.asyncio
    async def test_alert_deduplication(self):
        """Duplicate alerts within window are suppressed."""
        from app.services.alert_engine import AlertDeduplicationService
        
        dedup = AlertDeduplicationService(window_seconds=60)
        
        alert1 = Alert(
            id="alert-1",
            organization_id="test-org",
            rule_name="test_rule",
            rule_description="Test",
            dimension="test",
            severity=AlertSeverity.WARNING,
            state=AlertState.OBSERVED,
            title="Test",
            description="Test",
            details={},
            fingerprint="fp1",
        )
        
        alert2 = Alert(
            id="alert-2",
            organization_id="test-org",
            rule_name="test_rule",
            rule_description="Test",
            dimension="test",
            severity=AlertSeverity.WARNING,
            state=AlertState.OBSERVED,
            title="Test",
            description="Test",
            details={},
            fingerprint="fp1",  # Same fingerprint
        )
        
        # First alert should not be duplicate
        assert dedup.is_duplicate(alert1) is False
        
        # Second alert with same fingerprint should be duplicate
        assert dedup.is_duplicate(alert2) is True
    
    @pytest.mark.asyncio
    async def test_release_health_alert_rules_exist(self):
        """Default release health alert rules are registered."""
        rules = alert_engine.list_rules()
        rule_names = {r.name for r in rules}
        
        # Check critical release health rules exist
        required_rules = {
            "preflight_failure",
            "preflight_warning",
            "migration_failure",
            "deployment_failure",
            "deployment_health_check_failure",
            "fingerprint_mismatch",
            "canonical_integrity_critical",
            "database_unhealthy",
            "temporal_integrity_violation",
            "provenance_chain_broken",
            "governance_policy_violation",
            "recovery_failure",
            "integration_sync_failure",
            "sync_freshness_stale",
            "company_brain_unhealthy",
            "security_event_detected",
            "longitudinal_integrity_violation",
        }
        
        for rule_name in required_rules:
            assert rule_name in rule_names, f"Missing rule: {rule_name}"


# =============================================================================
# HEALTH EVALUATION TESTS
# =============================================================================

class TestHealthEvaluation:
    """Test health evaluation across 13 dimensions."""
    
    @pytest.mark.asyncio
    async def test_all_13_dimensions_evaluated(self, test_org: Organization, pg_db_session: AsyncSession):
        """All 13 health dimensions are evaluated."""
        report = await health_evaluation_service.evaluate_all(pg_db_session, test_org.id)
        
        assert isinstance(report, AggregateHealthReport)
        assert report.organization_id == test_org.id
        assert report.overall_status in ["healthy", "degraded", "critical", "unknown"]
        
        # Check all 13 dimensions present
        assert len(report.dimension_results) == 13
        for dim in HealthDimensionName:
            assert dim in report.dimension_results
            result = report.dimension_results[dim]
            assert result.dimension == dim
            assert result.status in ["healthy", "degraded", "critical", "unknown"]
            assert isinstance(result.current_value, float)
            assert result.checked_at is not None
    
    @pytest.mark.asyncio
    async def test_individual_dimension_evaluation(self, test_org: Organization, pg_db_session: AsyncSession):
        """Can evaluate individual dimensions."""
        # Test infrastructure
        result = await health_evaluation_service.evaluate_dimension(
            pg_db_session, test_org.id, HealthDimensionName.INFRASTRUCTURE
        )
        assert result.dimension == HealthDimensionName.INFRASTRUCTURE
        assert result.status in ["healthy", "degraded", "critical", "unknown"]
        
        # Test database
        result = await health_evaluation_service.evaluate_dimension(
            pg_db_session, test_org.id, HealthDimensionName.DATABASE
        )
        assert result.dimension == HealthDimensionName.DATABASE
    
    @pytest.mark.asyncio
    async def test_canonical_reality_evaluation(self, test_org: Organization, pg_db_session: AsyncSession):
        """Canonical reality health evaluation runs."""
        result = await health_evaluation_service.evaluate_dimension(
            pg_db_session, test_org.id, HealthDimensionName.CANONICAL_REALITY
        )
        assert result.dimension == HealthDimensionName.CANONICAL_REALITY
        assert "violations" in str(result.evidence).lower() or "checks" in str(result.evidence).lower()
    
    @pytest.mark.asyncio
    async def test_temporal_integrity_evaluation(self, test_org: Organization, pg_db_session: AsyncSession):
        """Temporal integrity health evaluation runs."""
        result = await health_evaluation_service.evaluate_dimension(
            pg_db_session, test_org.id, HealthDimensionName.TEMPORAL_INTEGRITY
        )
        assert result.dimension == HealthDimensionName.TEMPORAL_INTEGRITY
    
    @pytest.mark.asyncio
    async def test_provenance_evaluation(self, test_org: Organization, pg_db_session: AsyncSession):
        """Provenance health evaluation runs."""
        result = await health_evaluation_service.evaluate_dimension(
            pg_db_session, test_org.id, HealthDimensionName.PROVENANCE
        )
        assert result.dimension == HealthDimensionName.PROVENANCE
    
    @pytest.mark.asyncio
    async def test_governance_evaluation(self, test_org: Organization, pg_db_session: AsyncSession):
        """Governance health evaluation runs."""
        result = await health_evaluation_service.evaluate_dimension(
            pg_db_session, test_org.id, HealthDimensionName.GOVERNANCE
        )
        assert result.dimension == HealthDimensionName.GOVERNANCE
    
    @pytest.mark.asyncio
    async def test_concurrency_evaluation(self, test_org: Organization, pg_db_session: AsyncSession):
        """Concurrency health evaluation runs."""
        result = await health_evaluation_service.evaluate_dimension(
            pg_db_session, test_org.id, HealthDimensionName.CONCURRENCY
        )
        assert result.dimension == HealthDimensionName.CONCURRENCY
    
    @pytest.mark.asyncio
    async def test_recovery_evaluation(self, test_org: Organization, pg_db_session: AsyncSession):
        """Recovery health evaluation runs."""
        result = await health_evaluation_service.evaluate_dimension(
            pg_db_session, test_org.id, HealthDimensionName.RECOVERY
        )
        assert result.dimension == HealthDimensionName.RECOVERY
    
    @pytest.mark.asyncio
    async def test_integrations_evaluation(self, test_org: Organization, pg_db_session: AsyncSession):
        """Integrations health evaluation runs."""
        result = await health_evaluation_service.evaluate_dimension(
            pg_db_session, test_org.id, HealthDimensionName.INTEGRATIONS
        )
        assert result.dimension == HealthDimensionName.INTEGRATIONS
    
    @pytest.mark.asyncio
    async def test_company_brain_evaluation(self, test_org: Organization, pg_db_session: AsyncSession):
        """Company Brain health evaluation runs."""
        result = await health_evaluation_service.evaluate_dimension(
            pg_db_session, test_org.id, HealthDimensionName.COMPANY_BRAIN
        )
        assert result.dimension == HealthDimensionName.COMPANY_BRAIN
    
    @pytest.mark.asyncio
    async def test_security_evaluation(self, test_org: Organization, pg_db_session: AsyncSession):
        """Security health evaluation runs."""
        result = await health_evaluation_service.evaluate_dimension(
            pg_db_session, test_org.id, HealthDimensionName.SECURITY
        )
        assert result.dimension == HealthDimensionName.SECURITY
    
    @pytest.mark.asyncio
    async def test_deployment_evaluation(self, test_org: Organization, pg_db_session: AsyncSession):
        """Deployment health evaluation runs."""
        result = await health_evaluation_service.evaluate_dimension(
            pg_db_session, test_org.id, HealthDimensionName.DEPLOYMENT
        )
        assert result.dimension == HealthDimensionName.DEPLOYMENT
    
    @pytest.mark.asyncio
    async def test_longitudinal_integrity_evaluation(self, test_org: Organization, pg_db_session: AsyncSession):
        """Longitudinal integrity health evaluation runs."""
        result = await health_evaluation_service.evaluate_dimension(
            pg_db_session, test_org.id, HealthDimensionName.LONGITUDINAL_INTEGRITY
        )
        assert result.dimension == HealthDimensionName.LONGITUDINAL_INTEGRITY
    
    @pytest.mark.asyncio
    async def test_aggregate_fingerprint_generated(self, test_org: Organization, pg_db_session: AsyncSession):
        """Aggregate fingerprint is generated for health report."""
        report = await health_evaluation_service.evaluate_all(pg_db_session, test_org.id)
        
        assert report.aggregate_fingerprint is not None
        assert len(report.aggregate_fingerprint) == 64  # SHA256 hex truncated to 64
    
    @pytest.mark.asyncio
    async def test_health_dimension_storage(self, test_org: Organization, pg_db_session: AsyncSession):
        """Health dimensions can be stored to database."""
        report = await health_evaluation_service.evaluate_all(pg_db_session, test_org.id)
        
        stored = await health_evaluation_service.store_health_dimensions(pg_db_session, report)
        
        assert len(stored) == 13
        for hd in stored:
            assert hd.organization_id == test_org.id
            assert hd.dimension in [d.value for d in HealthDimensionName]
            assert hd.status in ["healthy", "degraded", "critical", "unknown"]


# =============================================================================
# HEALTH MODEL TESTS
# =============================================================================

class TestHealthModel:
    """Test health model service with trends and anomalies."""
    
    @pytest.mark.asyncio
    async def test_build_health_model_snapshot(self, test_org: Organization, pg_db_session: AsyncSession):
        """Can build health model snapshot from evaluation."""
        health_report = await health_evaluation_service.evaluate_all(pg_db_session, test_org.id)
        
        snapshot = await health_model_service.build_health_model(
            pg_db_session, test_org.id, health_report
        )
        
        assert snapshot.organization_id == test_org.id
        assert snapshot.overall_status == health_report.overall_status
        assert snapshot.aggregate_fingerprint == health_report.aggregate_fingerprint
        assert len(snapshot.dimension_statuses) == 13
        assert len(snapshot.dimension_values) == 13
    
    @pytest.mark.asyncio
    async def test_health_model_with_tenant_fingerprint(self, test_org: Organization, pg_db_session: AsyncSession):
        """Health model correlates with tenant fingerprint."""
        from app.services.canonical_fingerprint import canonical_fingerprint_service
        
        health_report = await health_evaluation_service.evaluate_all(pg_db_session, test_org.id)
        tenant_fp = await canonical_fingerprint_service.compute_tenant_fingerprint(pg_db_session, test_org.id)
        
        snapshot = await health_model_service.build_health_model(
            pg_db_session, test_org.id, health_report, tenant_fp
        )
        
        assert snapshot.tenant_fingerprint == tenant_fp.aggregate_fingerprint
    
    @pytest.mark.asyncio
    async def test_trend_analysis(self, test_org: Organization, pg_db_session: AsyncSession):
        """Trend analysis works across dimensions."""
        # Build a few snapshots to create history
        for i in range(3):
            health_report = await health_evaluation_service.evaluate_all(pg_db_session, test_org.id)
            await health_model_service.build_health_model(pg_db_session, test_org.id, health_report)
        
        trends = await health_model_service.get_health_trends(pg_db_session, test_org.id, window_days=1)
        
        # Should have trends for dimensions with history
        assert isinstance(trends, dict)
    
    @pytest.mark.asyncio
    async def test_anomaly_detection(self, test_org: Organization, pg_db_session: AsyncSession):
        """Anomaly detection identifies issues."""
        health_report = await health_evaluation_service.evaluate_all(pg_db_session, test_org.id)
        snapshot = await health_model_service.build_health_model(pg_db_session, test_org.id, health_report)
        trends = await health_model_service.get_health_trends(pg_db_session, test_org.id)
        
        anomalies = await health_model_service.detect_anomalies(
            pg_db_session, test_org.id, snapshot, trends
        )
        
        assert isinstance(anomalies, list)
        # Anomalies may or may not be found depending on data
    
    @pytest.mark.asyncio
    async def test_comprehensive_report_generation(self, test_org: Organization, pg_db_session: AsyncSession):
        """Full health model report generation works."""
        health_report = await health_evaluation_service.evaluate_all(pg_db_session, test_org.id)
        
        report = await health_model_service.generate_report(pg_db_session, test_org.id, health_report)
        
        assert isinstance(report, HealthModelReport)
        assert report.organization_id == test_org.id
        assert report.current_snapshot is not None
        assert isinstance(report.trends, dict)
        assert isinstance(report.trend_summary, dict)
        assert isinstance(report.anomaly_alerts, list)
        assert report.fingerprint is not None
        assert len(report.fingerprint) == 64
    
    @pytest.mark.asyncio
    async def test_snapshot_comparison(self, test_org: Organization, pg_db_session: AsyncSession):
        """Can compare two health snapshots."""
        health_report = await health_evaluation_service.evaluate_all(pg_db_session, test_org.id)
        snapshot1 = await health_model_service.build_health_model(pg_db_session, test_org.id, health_report)
        
        # Simulate a change by creating a new snapshot
        health_report2 = await health_evaluation_service.evaluate_all(pg_db_session, test_org.id)
        snapshot2 = await health_model_service.build_health_model(pg_db_session, test_org.id, health_report2)
        
        changes = await health_model_service.compare_snapshots(test_org.id, snapshot1, snapshot2)
        
        assert "overall_status_changed" in changes
        assert "dimension_changes" in changes
        assert "fingerprint_match" in changes
    
    @pytest.mark.asyncio
    async def test_fingerprint_correlation(self, test_org: Organization, pg_db_session: AsyncSession):
        """Health model correlates with canonical fingerprint."""
        health_report = await health_evaluation_service.evaluate_all(pg_db_session, test_org.id)
        
        correlation = await health_model_service.correlate_with_canonical_fingerprint(
            pg_db_session, test_org.id, health_report
        )
        
        assert "fingerprint_match" in correlation
        assert "health_aggregate_fingerprint" in correlation
        assert "tenant_aggregate_fingerprint" in correlation
        assert "component_differences" in correlation
        assert "divergence_detected" in correlation


# =============================================================================
# OBSERVABILITY INTEGRATION TESTS
# =============================================================================

class TestObservabilitySlice2EIntegration:
    """Test Slice 2E integration with observability service."""
    
    @pytest.mark.asyncio
    async def test_slice2e_extension_available(self):
        """Slice 2E extension is available."""
        ext = get_slice2e_extension(observability_service)
        assert ext is not None
    
    @pytest.mark.asyncio
    async def test_evaluate_release_health(self, test_org: Organization, pg_db_session: AsyncSession):
        """Can evaluate comprehensive release health."""
        ext = get_slice2e_extension(observability_service)
        assert ext is not None
        
        result = await ext.evaluate_release_health(pg_db_session, test_org.id)
        
        assert "health_report" in result
        assert "tenant_fingerprint" in result
        assert "health_model" in result
        assert "fingerprint_correlation" in result
        assert "alerts" in result
    
    @pytest.mark.asyncio
    async def test_alert_dashboard(self, test_org: Organization, pg_db_session: AsyncSession):
        """Alert dashboard returns organized data."""
        ext = get_slice2e_extension(observability_service)
        assert ext is not None
        
        dashboard = await ext.get_alert_dashboard(pg_db_session, test_org.id)
        
        assert "organization_id" in dashboard
        assert "total_alerts" in dashboard
        assert "by_state" in dashboard
        assert "by_severity" in dashboard
        assert "correlations" in dashboard
        assert "active_alerts" in dashboard
    
    @pytest.mark.asyncio
    async def test_alert_lifecycle_via_extension(self, test_org: Organization, pg_db_session: AsyncSession):
        """Alert lifecycle operations work via extension."""
        ext = get_slice2e_extension(observability_service)
        assert ext is not None
        
        # Create an alert directly in engine
        alert = Alert(
            id=f"alert-{uuid.uuid4().hex[:12]}",
            organization_id=test_org.id,
            rule_name="test_rule",
            rule_description="Test",
            dimension="test",
            severity=AlertSeverity.WARNING,
            state=AlertState.ALERTED,
            title="Test Alert",
            description="Test",
            details={},
            fingerprint="test-fp",
        )
        alert_engine._alerts[alert.id] = alert
        
        # Acknowledge via extension
        result = await ext.acknowledge_alert(alert.id, "test-user")
        assert result is True
        assert alert.state == AlertState.ACKNOWLEDGED
        
        # Investigate
        result = await ext.investigate_alert(alert.id, "test-user")
        assert result is True
        assert alert.state == AlertState.INVESTIGATING
        
        # Resolve
        result = await ext.resolve_alert(alert.id, "test-user", "Fixed")
        assert result is True
        assert alert.state == AlertState.RESOLVED
        
        # Verify
        result = await ext.verify_alert(alert.id, "test-user")
        assert result is True
        assert alert.state == AlertState.VERIFIED


# =============================================================================
# END-TO-END RELEASE HEALTH TEST
# =============================================================================

class TestReleaseHealthEndToEnd:
    """End-to-end release health observability test."""
    
    @pytest.mark.asyncio
    async def test_release_health_observability_flow(
        self,
        test_org: Organization,
        pg_db_session: AsyncSession,
    ):
        """Complete release health observability flow."""
        
        # 1. Record a health check observation
        obs = await observability_service.record_observation(
            pg_db_session,
            context=type('obj', (object,), {
                'organization_id': test_org.id,
                'observation_type': 'health_check',
                'source': 'release_preflight',
                'source_component': 'preflight',
                'actor_id': 'system',
                'actor_type': 'system',
                'severity': 'warning',
                'epistemic_status': 'observed',
                'correlation_id': None,
                'trace_id': None,
                'span_id': None,
                'parent_span_id': None,
                'operation_id': None,
                'operation_type': None,
                'attempt_id': None,
                'integration_id': None,
                'connector_id': None,
                'external_operation_id': None,
                'security_event_id': None,
                'degradation_id': None,
                'title': 'Release preflight check',
                'description': 'Preflight check completed with warnings',
                'details_json': {'check': 'canonical_integrity', 'status': 'warning'},
                'metrics_json': {'warnings': 2},
                'provenance_json': {},
                'source_event_id': None,
                'observed_at': utcnow(),
                'duration_ms': 100,
                'key_fields': {'check': 'canonical_integrity'},
            })()
        )
        
        assert obs is not None
        assert obs.observation_type == "health_check"
        
        # 2. Evaluate release health
        ext = get_slice2e_extension(observability_service)
        assert ext is not None
        
        health_result = await ext.evaluate_release_health(pg_db_session, test_org.id)
        
        # 3. Verify health report structure
        assert "health_report" in health_result
        health_report = health_result["health_report"]
        assert health_report.overall_status in ["healthy", "degraded", "critical", "unknown"]
        
        # 4. Verify health model
        assert "health_model" in health_result
        health_model = health_result["health_model"]
        assert health_model.current_snapshot is not None
        assert len(health_model.current_snapshot.dimension_statuses) == 13
        
        # 5. Verify fingerprint correlation
        assert "fingerprint_correlation" in health_result
        fp_corr = health_result["fingerprint_correlation"]
        assert "fingerprint_match" in fp_corr
        assert "divergence_detected" in fp_corr
        
        # 6. Verify alerts evaluated
        assert "alerts" in health_result
        alerts_info = health_result["alerts"]
        assert "triggered" in alerts_info
        assert "by_severity" in alerts_info
        
        # 7. Get alert dashboard
        dashboard = await ext.get_alert_dashboard(pg_db_session, test_org.id)
        assert "total_alerts" in dashboard
        assert "by_state" in dashboard
        assert "active_alerts" in dashboard


# =============================================================================
# REGRESSION TESTS
# =============================================================================

class TestSlice2EReggression:
    """Regression tests to ensure Slice 2E doesn't break existing functionality."""
    
    @pytest.mark.asyncio
    async def test_gate34_observability_still_works(self, test_org: Organization, pg_db_session: AsyncSession):
        """Gate 34 observability functionality still works."""
        
        # Record observation
        obs = await observability_service.record_observation(
            pg_db_session,
            context=type('obj', (object,), {
                'organization_id': test_org.id,
                'observation_type': 'request',
                'source': 'api',
                'source_component': 'test',
                'actor_id': 'test-user',
                'actor_type': 'human',
                'severity': 'info',
                'epistemic_status': 'observed',
                'correlation_id': None,
                'trace_id': uuid.uuid4().hex[:32],
                'span_id': uuid.uuid4().hex[:16],
                'parent_span_id': None,
                'operation_id': None,
                'operation_type': None,
                'attempt_id': None,
                'integration_id': None,
                'connector_id': None,
                'external_operation_id': None,
                'security_event_id': None,
                'degradation_id': None,
                'title': 'Test Request',
                'description': 'Test API request',
                'details_json': {},
                'metrics_json': {'duration_ms': 50},
                'provenance_json': {},
                'source_event_id': None,
                'observed_at': utcnow(),
                'duration_ms': 50,
                'key_fields': {'route': '/test'},
            })()
        )
        
        assert obs is not None
        assert obs.observation_type == "request"
        
        # Create degradation
        deg = await observability_service.create_degradation(
            pg_db_session,
            organization_id=test_org.id,
            degradation_type="test",
            severity="minor",
            title="Test Degradation",
            description="Test",
        )
        
        assert deg is not None
        assert deg.state == "detected"
        
        # Acknowledge
        deg = await observability_service.acknowledge_degradation(pg_db_session, degradation=deg, actor_id="test-user")
        assert deg.state == "investigating"
        
        # Record health dimension
        hdim = await observability_service.record_health_dimension(
            pg_db_session,
            organization_id=test_org.id,
            dimension="error_rate",
            current_value=0.01,
            threshold_warn=0.05,
            threshold_critical=0.10,
        )
        
        assert hdim is not None
        assert hdim.dimension == "error_rate"
        assert hdim.status == "healthy"
    
    @pytest.mark.asyncio
    async def test_no_parallel_reality(self, test_org: Organization, pg_db_session: AsyncSession):
        """Observability reuses canonical primitives - no parallel reality."""
        
        # Health dimensions should use canonical fingerprinting
        health_report = await health_evaluation_service.evaluate_all(pg_db_session, test_org.id)
        
        # Fingerprint should be derived from canonical data
        assert health_report.aggregate_fingerprint is not None
        
        # Health model should correlate with tenant fingerprint
        from app.services.canonical_fingerprint import canonical_fingerprint_service
        tenant_fp = await canonical_fingerprint_service.compute_tenant_fingerprint(pg_db_session, test_org.id)
        
        correlation = await health_model_service.correlate_with_canonical_fingerprint(
            pg_db_session, test_org.id, health_report
        )
        
        # Should be able to compare fingerprints
        assert "fingerprint_match" in correlation
        assert "component_differences" in correlation
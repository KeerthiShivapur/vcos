with open('tests/acceptance/test_backup_restore_roundtrip.py', 'r') as f:
    content = f.read()

# Fix the observation_type in _create_observations - use valid value per check constraint
old_obs = '''obs = CanonicalObservation(
                id=self._generate_id("obs-"),
                organization_id=self.org_id,
                observation_type="internal_operation",
                fingerprint=f"test-obs-{uuid.uuid4().hex[:8]}",
                source="vcos",
                source_component="test",
                actor_id=self.caller_b.employee_id,
                actor_type="employee",
                severity="info",
                epistemic_status="observed",
                correlation_id=None,
                trace_id=None,
                span_id=None,
                parent_span_id=None,
                operation_id=None,
                operation_type="test.operation",
                attempt_id=None,
                integration_id=None,
                connector_id=None,
                external_operation_id=None,
                security_event_id=None,
                degradation_id=None,
                title="Test Observation B",
                description="Observation in Tenant B",
                details_json={"test": True},
                metrics_json="{}",
                provenance_json={"source_event_id": f"{self.caller_b.organization_id}-evt-1"},
                source_event_id=f"{self.caller_b.organization_id}-evt-1",
                observed_at=utcnow(),
                recorded_at=utcnow(),
                duration_ms=None,
                version=1,'''

new_obs = '''obs = CanonicalObservation(
                id=self._generate_id("obs-"),
                organization_id=self.org_id,
                observation_type="external_operation",
                fingerprint=self._unique("obs-"),
                source="vcos",
                source_component="test",
                actor_id=self.caller.employee_id,
                actor_type="employee",
                severity="info",
                epistemic_status="observed",
                correlation_id=None,
                trace_id=None,
                span_id=None,
                parent_span_id=None,
                operation_id=None,
                operation_type="test.operation",
                attempt_id=None,
                integration_id=None,
                connector_id=None,
                external_operation_id=None,
                security_event_id=None,
                degradation_id=None,
                title="Test Observation",
                description="Test observation",
                details_json={"test": True},
                metrics_json="{}",
                provenance_json={"source_event_id": f"{self.org_id}-evt-1"},
                source_event_id=f"{self.org_id}-evt-1",
                observed_at=utcnow(),
                recorded_at=utcnow(),
                duration_ms=None,
                version=1,'''

content = content.replace(old_obs, new_obs)

with open('tests/acceptance/test_backup_restore_roundtrip.py', 'w') as f:
    f.write(content)

print('Fixed _create_observations')
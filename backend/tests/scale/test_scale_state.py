"""Tests for Scale Run State Machine."""

import pytest
import uuid
from datetime import datetime
from tests.scale.scale_state import (
    ScaleRunState,
    ScaleRunPhase,
    ScaleRunCheckpoint,
    DatasetIdentity,
    ScaleRunOwnership,
    ScaleRunMetadata,
    ScaleRunStateStore,
    ScaleRunStateMachine,
    create_dataset_identity,
)


class TestDatasetIdentity:
    
    def test_dataset_identity_creation(self):
        identity = create_dataset_identity(
            vcos_revision="abc123",
            schema_revision="schema_v1",
            generator_revision="gen_v1",
            scale_profile="large_5k",
            employee_count=5000,
            tenant_count=1,
            seed=42,
            density_strategy="standard",
            environment_fingerprint="fp_123",
        )
        
        assert identity.vcos_revision == "abc123"
        assert identity.employee_count == 5000
        assert identity.tenant_count == 1
        assert identity.seed == 42
    
    def test_dataset_identity_deterministic_hash(self):
        identity1 = create_dataset_identity(
            vcos_revision="abc123",
            schema_revision="schema_v1",
            generator_revision="gen_v1",
            scale_profile="large_5k",
            employee_count=5000,
            tenant_count=1,
            seed=42,
            density_strategy="standard",
            environment_fingerprint="fp_123",
        )
        
        identity2 = create_dataset_identity(
            vcos_revision="abc123",
            schema_revision="schema_v1",
            generator_revision="gen_v1",
            scale_profile="large_5k",
            employee_count=5000,
            tenant_count=1,
            seed=42,
            density_strategy="standard",
            environment_fingerprint="fp_123",
        )
        
        assert identity1.to_hash() == identity2.to_hash()
    
    def test_dataset_identity_different_inputs_different_hash(self):
        identity1 = create_dataset_identity(
            vcos_revision="abc123",
            schema_revision="schema_v1",
            generator_revision="gen_v1",
            scale_profile="large_5k",
            employee_count=5000,
            tenant_count=1,
            seed=42,
            density_strategy="standard",
            environment_fingerprint="fp_123",
        )
        
        identity2 = create_dataset_identity(
            vcos_revision="abc123",
            schema_revision="schema_v1",
            generator_revision="gen_v1",
            scale_profile="large_5k",
            employee_count=5000,
            tenant_count=1,
            seed=43,  # Different seed
            density_strategy="standard",
            environment_fingerprint="fp_123",
        )
        
        assert identity1.to_hash() != identity2.to_hash()


class TestScaleRunMetadata:
    
    def test_metadata_creation(self):
        identity = create_dataset_identity(
            vcos_revision="abc123",
            schema_revision="schema_v1",
            generator_revision="gen_v1",
            scale_profile="large_5k",
            employee_count=5000,
            tenant_count=1,
            seed=42,
            density_strategy="standard",
            environment_fingerprint="fp_123",
        )
        
        ownership = ScaleRunOwnership(
            run_id="test_run_123",
            owns_database=True,
            database_name="vcos_scale_5k_test",
        )
        
        metadata = ScaleRunMetadata(
            run_id="test_run_123",
            state=ScaleRunState.CREATED,
            profile_name="large_5k",
            employee_count=5000,
            tenant_count=1,
            environment_type="external",
            dataset_identity=identity,
            ownership=ownership,
        )
        
        assert metadata.run_id == "test_run_123"
        assert metadata.state == ScaleRunState.CREATED
        assert metadata.profile_name == "large_5k"
        assert metadata.employee_count == 5000
    
    def test_metadata_serialization(self):
        identity = create_dataset_identity(
            vcos_revision="abc123",
            schema_revision="schema_v1",
            generator_revision="gen_v1",
            scale_profile="large_5k",
            employee_count=5000,
            tenant_count=1,
            seed=42,
            density_strategy="standard",
            environment_fingerprint="fp_123",
        )
        
        ownership = ScaleRunOwnership(
            run_id="test_run_123",
            owns_database=True,
            database_name="vcos_scale_5k_test",
        )
        
        metadata = ScaleRunMetadata(
            run_id="test_run_123",
            state=ScaleRunState.CREATED,
            profile_name="large_5k",
            employee_count=5000,
            tenant_count=1,
            environment_type="external",
            dataset_identity=identity,
            ownership=ownership,
        )
        
        data = metadata.to_dict()
        restored = ScaleRunMetadata.from_dict(data)
        
        assert restored.run_id == metadata.run_id
        assert restored.state == metadata.state
        assert restored.profile_name == metadata.profile_name
        assert restored.employee_count == metadata.employee_count
        assert restored.dataset_identity.to_hash() == metadata.dataset_identity.to_hash()


class TestScaleRunStateMachine:
    
    def test_state_machine_creation(self):
        store = ScaleRunStateStore()
        machine = ScaleRunStateMachine(store)
        
        identity = create_dataset_identity(
            vcos_revision="abc123",
            schema_revision="schema_v1",
            generator_revision="gen_v1",
            scale_profile="large_5k",
            employee_count=5000,
            tenant_count=1,
            seed=42,
            density_strategy="standard",
            environment_fingerprint="fp_123",
        )
        
        ownership = ScaleRunOwnership(
            run_id="test_run_123",
            owns_database=True,
            database_name="vcos_scale_5k_test",
        )
        
        metadata = machine.create_run(
            profile_name="large_5k",
            employee_count=5000,
            tenant_count=1,
            environment_type="external",
            dataset_identity=identity,
            ownership=ownership,
            run_id="test_run_123",
        )
        
        assert metadata.run_id == "test_run_123"
        assert metadata.state == ScaleRunState.CREATED
    
    def test_valid_transitions(self):
        store = ScaleRunStateStore()
        machine = ScaleRunStateMachine(store)
        
        identity = create_dataset_identity(
            vcos_revision="abc123",
            schema_revision="schema_v1",
            generator_revision="gen_v1",
            scale_profile="large_5k",
            employee_count=5000,
            tenant_count=1,
            seed=42,
            density_strategy="standard",
            environment_fingerprint="fp_123",
        )
        
        ownership = ScaleRunOwnership(run_id="test_run_123")
        
        machine.create_run(
            profile_name="large_5k",
            employee_count=5000,
            tenant_count=1,
            environment_type="external",
            dataset_identity=identity,
            ownership=ownership,
            run_id="test_run_123",
        )
        
        # Valid transitions
        machine.transition(ScaleRunState.PREFLIGHTED)
        assert machine.get_current().state == ScaleRunState.PREFLIGHTED
        
        machine.transition(ScaleRunState.INITIALIZED)
        assert machine.get_current().state == ScaleRunState.INITIALIZED
        
        machine.transition(ScaleRunState.SCHEMA_READY)
        assert machine.get_current().state == ScaleRunState.SCHEMA_READY
        
        machine.transition(ScaleRunState.GENERATING)
        assert machine.get_current().state == ScaleRunState.GENERATING
        
        machine.transition(ScaleRunState.DATA_GENERATED)
        assert machine.get_current().state == ScaleRunState.DATA_GENERATED
        
        machine.transition(ScaleRunState.INTEGRITY_VALIDATED)
        assert machine.get_current().state == ScaleRunState.INTEGRITY_VALIDATED
        
        machine.transition(ScaleRunState.QUERY_VALIDATED)
        assert machine.get_current().state == ScaleRunState.QUERY_VALIDATED
        
        machine.transition(ScaleRunState.PERFORMANCE_MEASURED)
        assert machine.get_current().state == ScaleRunState.PERFORMANCE_MEASURED
        
        machine.transition(ScaleRunState.FINGERPRINTED)
        assert machine.get_current().state == ScaleRunState.FINGERPRINTED
        
        machine.transition(ScaleRunState.CLEANUP)
        assert machine.get_current().state == ScaleRunState.CLEANUP
        
        machine.transition(ScaleRunState.COMPLETED)
        assert machine.get_current().state == ScaleRunState.COMPLETED
    
    def test_invalid_transition_raises(self):
        store = ScaleRunStateStore()
        machine = ScaleRunStateMachine(store)
        
        identity = create_dataset_identity(
            vcos_revision="abc123",
            schema_revision="schema_v1",
            generator_revision="gen_v1",
            scale_profile="large_5k",
            employee_count=5000,
            tenant_count=1,
            seed=42,
            density_strategy="standard",
            environment_fingerprint="fp_123",
        )
        
        ownership = ScaleRunOwnership(run_id="test_run_123")
        
        machine.create_run(
            profile_name="large_5k",
            employee_count=5000,
            tenant_count=1,
            environment_type="external",
            dataset_identity=identity,
            ownership=ownership,
            run_id="test_run_123",
        )
        
        # Invalid: CREATED -> COMPLETED
        with pytest.raises(ValueError):
            machine.transition(ScaleRunState.COMPLETED)
    
    def test_retry_after_failure(self):
        store = ScaleRunStateStore()
        machine = ScaleRunStateMachine(store)
        
        identity = create_dataset_identity(
            vcos_revision="abc123",
            schema_revision="schema_v1",
            generator_revision="gen_v1",
            scale_profile="large_5k",
            employee_count=5000,
            tenant_count=1,
            seed=42,
            density_strategy="standard",
            environment_fingerprint="fp_123",
        )
        
        ownership = ScaleRunOwnership(run_id="test_run_123")
        
        machine.create_run(
            profile_name="large_5k",
            employee_count=5000,
            tenant_count=1,
            environment_type="external",
            dataset_identity=identity,
            ownership=ownership,
            run_id="test_run_123",
        )
        
        machine.transition(ScaleRunState.FAILED, error="Test failure")
        assert machine.get_current().state == ScaleRunState.FAILED
        assert machine.can_retry() is True
        
        machine.increment_retry()
        assert machine.get_current().state == ScaleRunState.CREATED
        assert machine.get_current().retry_count == 1
    
    def test_checkpoint_recording(self):
        store = ScaleRunStateStore()
        machine = ScaleRunStateMachine(store)
        
        identity = create_dataset_identity(
            vcos_revision="abc123",
            schema_revision="schema_v1",
            generator_revision="gen_v1",
            scale_profile="large_5k",
            employee_count=5000,
            tenant_count=1,
            seed=42,
            density_strategy="standard",
            environment_fingerprint="fp_123",
        )
        
        ownership = ScaleRunOwnership(run_id="test_run_123")
        
        machine.create_run(
            profile_name="large_5k",
            employee_count=5000,
            tenant_count=1,
            environment_type="external",
            dataset_identity=identity,
            ownership=ownership,
            run_id="test_run_123",
        )
        
        # Follow valid state transitions
        machine.transition(ScaleRunState.PREFLIGHTED)
        machine.transition(ScaleRunState.INITIALIZED)
        machine.transition(ScaleRunState.SCHEMA_READY)
        machine.transition(ScaleRunState.GENERATING)
        
        checkpoint = ScaleRunCheckpoint(
            run_id="test_run_123",
            phase=ScaleRunPhase.GENERATION,
            entity_type="employees",
            batch_number=1,
            rows_created=5000,
            rows_expected=5000,
            started_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
        )
        
        machine.add_checkpoint(checkpoint)
        
        current = machine.get_current()
        assert len(current.checkpoints) == 1
        assert current.checkpoints[0].entity_type == "employees"
        assert current.checkpoints[0].rows_created == 5000


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
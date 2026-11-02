"""Tests for Scale Run Manifest."""

import pytest
import json
from pathlib import Path
from tests.scale.run_manifest import (
    ScaleRunManifest,
    ManifestSchemaVersion,
    create_scale_run_manifest,
)


class TestScaleRunManifest:
    
    def test_manifest_creation(self):
        manifest = create_scale_run_manifest(
            run_id="test_123",
            scale_profile="large_10k",
            employee_count=10000,
            tenant_count=1,
            seed=42,
            density_strategy="standard",
            dataset_identity={"hash": "abc123"},
            environment_fingerprint={"fp": "xyz789"},
            schema_revision="schema_v1",
            vcos_revision="abc123",
            generator_revision="gen_v1",
            evidence_schema_version="1.0",
        )
        
        assert manifest.run_id == "test_123"
        assert manifest.scale_profile == "large_10k"
        assert manifest.employee_count == 10000
        assert manifest.tenant_count == 1
        assert manifest.seed == 42
        assert manifest.manifest_schema_version == "1.0"
        assert manifest.start_time != ""
    
    def test_manifest_serialization(self):
        manifest = create_scale_run_manifest(
            run_id="test_123",
            scale_profile="large_10k",
            employee_count=10000,
            tenant_count=1,
            seed=42,
            density_strategy="standard",
            dataset_identity={"hash": "abc123"},
            environment_fingerprint={"fp": "xyz789"},
            schema_revision="schema_v1",
            vcos_revision="abc123",
            generator_revision="gen_v1",
            evidence_schema_version="1.0",
        )
        
        manifest.end_time = "2024-01-01T00:00:00"
        manifest.acceptance_result = "PASS"
        manifest.acceptance_reason = "All checks passed"
        
        json_str = manifest.to_json()
        assert "test_123" in json_str
        assert "large_10k" in json_str
        assert "PASS" in json_str
    
    def test_manifest_deserialization(self):
        manifest = create_scale_run_manifest(
            run_id="test_123",
            scale_profile="large_10k",
            employee_count=10000,
            tenant_count=1,
            seed=42,
            density_strategy="standard",
            dataset_identity={"hash": "abc123"},
            environment_fingerprint={"fp": "xyz789"},
            schema_revision="schema_v1",
            vcos_revision="abc123",
            generator_revision="gen_v1",
            evidence_schema_version="1.0",
        )
        
        json_str = manifest.to_json()
        restored = ScaleRunManifest.from_json(json_str)
        
        assert restored.run_id == manifest.run_id
        assert restored.scale_profile == manifest.scale_profile
        assert restored.employee_count == manifest.employee_count
        assert restored.dataset_identity == manifest.dataset_identity
    
    def test_deterministic_fingerprint(self):
        manifest1 = create_scale_run_manifest(
            run_id="test_123",
            scale_profile="large_10k",
            employee_count=10000,
            tenant_count=1,
            seed=42,
            density_strategy="standard",
            dataset_identity={"hash": "abc123"},
            environment_fingerprint={"fp": "xyz789"},
            schema_revision="schema_v1",
            vcos_revision="abc123",
            generator_revision="gen_v1",
            evidence_schema_version="1.0",
        )
        
        manifest2 = create_scale_run_manifest(
            run_id="test_123",
            scale_profile="large_10k",
            employee_count=10000,
            tenant_count=1,
            seed=42,
            density_strategy="standard",
            dataset_identity={"hash": "abc123"},
            environment_fingerprint={"fp": "xyz789"},
            schema_revision="schema_v1",
            vcos_revision="abc123",
            generator_revision="gen_v1",
            evidence_schema_version="1.0",
        )
        
        manifest1.end_time = "2024-01-01T00:00:00"
        manifest1.acceptance_result = "PASS"
        
        manifest2.end_time = "2024-01-02T00:00:00"
        manifest2.acceptance_result = "FAIL"
        
        # Fingerprint should be same despite different timestamps/results
        fp1 = manifest1.compute_fingerprint()
        fp2 = manifest2.compute_fingerprint()
        
        assert fp1 == fp2
        assert len(fp1) == 32  # SHA256 truncated to 32 chars
    
    def test_fingerprint_different_inputs(self):
        manifest1 = create_scale_run_manifest(
            run_id="test_123",
            scale_profile="large_10k",
            employee_count=10000,
            tenant_count=1,
            seed=42,
            density_strategy="standard",
            dataset_identity={"hash": "abc123"},
            environment_fingerprint={"fp": "xyz789"},
            schema_revision="schema_v1",
            vcos_revision="abc123",
            generator_revision="gen_v1",
            evidence_schema_version="1.0",
        )
        
        manifest2 = create_scale_run_manifest(
            run_id="test_123",
            scale_profile="large_10k",
            employee_count=10000,
            tenant_count=1,
            seed=43,  # Different seed
            density_strategy="standard",
            dataset_identity={"hash": "abc123"},
            environment_fingerprint={"fp": "xyz789"},
            schema_revision="schema_v1",
            vcos_revision="abc123",
            generator_revision="gen_v1",
            evidence_schema_version="1.0",
        )
        
        fp1 = manifest1.compute_fingerprint()
        fp2 = manifest2.compute_fingerprint()
        
        assert fp1 != fp2
    
    def test_schema_version_enum(self):
        assert ManifestSchemaVersion.V1.value == "1.0"
    
    def test_save_manifest(self, tmp_path):
        manifest = create_scale_run_manifest(
            run_id="test_123",
            scale_profile="large_10k",
            employee_count=10000,
            tenant_count=1,
            seed=42,
            density_strategy="standard",
            dataset_identity={"hash": "abc123"},
            environment_fingerprint={"fp": "xyz789"},
            schema_revision="schema_v1",
            vcos_revision="abc123",
            generator_revision="gen_v1",
            evidence_schema_version="1.0",
        )
        
        output_dir = str(tmp_path / "manifests")
        filepath = manifest.save(output_dir)
        
        # Verify file exists
        assert Path(filepath).exists()
        
        # Verify content
        with open(filepath, 'r') as f:
            data = json.load(f)
        
        assert data["run_id"] == "test_123"
        assert data["scale_profile"] == "large_10k"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
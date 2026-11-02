"""Scale Run Manifest.

Deterministic provenance record for authoritative scale validation runs.
This is test execution provenance - NOT a business/domain model.
"""

import json
import hashlib
import uuid
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, List, Optional
from datetime import datetime
from enum import Enum


class ManifestSchemaVersion(Enum):
    """Manifest schema versions for backward compatibility."""
    V1 = "1.0"


@dataclass
class ScaleRunManifest:
    """Complete manifest for an authoritative scale validation run.
    
    This is a TEST EXECUTION PROVENANCE artifact - NOT a business/domain model.
    It provides reproducibility and auditability for scale validation runs.
    """
    
    # Run identification
    run_id: str
    manifest_schema_version: str = "1.0"
    
    # Scale configuration
    scale_profile: str = ""
    employee_count: int = 0
    tenant_count: int = 0
    seed: int = 42
    density_strategy: str = "standard"
    
    # Identity & Versioning
    dataset_identity: Dict[str, Any] = field(default_factory=dict)
    environment_fingerprint: Dict[str, Any] = field(default_factory=dict)
    schema_revision: str = "unknown"
    vcos_revision: str = "unknown"
    generator_revision: str = "unknown"
    evidence_schema_version: str = "1.0"
    
    # Timing
    start_time: str = ""
    end_time: Optional[str] = None
    duration_seconds: float = 0.0
    
    # Result
    acceptance_result: Optional[str] = None
    acceptance_reason: str = ""
    
    # Evidence reference
    evidence_artifact_path: Optional[str] = None
    
    # Verification
    manifest_fingerprint: str = ""
    
    def __post_init__(self):
        if not self.run_id:
            self.run_id = str(uuid.uuid4())[:12]
        if not self.start_time:
            self.start_time = datetime.utcnow().isoformat()
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary, excluding secrets."""
        data = asdict(self)
        return data
    
    def to_json(self, indent: int = 2) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), indent=indent, default=str)
    
    def compute_fingerprint(self) -> str:
        """Generate deterministic fingerprint for this manifest.
        
        Excludes timestamps and result for reproducibility.
        """
        fingerprint_data = {
            "run_id": self.run_id,
            "scale_profile": self.scale_profile,
            "employee_count": self.employee_count,
            "tenant_count": self.tenant_count,
            "seed": self.seed,
            "density_strategy": self.density_strategy,
            "dataset_identity": self.dataset_identity,
            "schema_revision": self.schema_revision,
            "vcos_revision": self.vcos_revision,
            "generator_revision": self.generator_revision,
            "evidence_schema_version": self.evidence_schema_version,
            "manifest_schema_version": self.manifest_schema_version,
        }
        content = json.dumps(fingerprint_data, sort_keys=True, default=str)
        fingerprint = hashlib.sha256(content.encode()).hexdigest()[:32]
        self.manifest_fingerprint = fingerprint
        return fingerprint
    
    @classmethod
    def from_json(cls, json_str: str) -> 'ScaleRunManifest':
        """Deserialize from JSON."""
        data = json.loads(json_str)
        return cls(**data)
    
    def save(self, output_dir: str = "scale_manifests") -> str:
        """Save manifest artifact to file."""
        from pathlib import Path
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        filename = f"manifest_{self.scale_profile}_{self.run_id}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
        filepath = output_path / filename
        
        with open(filepath, 'w') as f:
            f.write(self.to_json())
        
        return str(filepath)


def create_scale_run_manifest(
    run_id: str,
    scale_profile: str,
    employee_count: int,
    tenant_count: int,
    seed: int,
    density_strategy: str,
    dataset_identity: Dict[str, Any],
    environment_fingerprint: Dict[str, Any],
    schema_revision: str,
    vcos_revision: str,
    generator_revision: str,
    evidence_schema_version: str,
) -> ScaleRunManifest:
    """Factory function to create initialized ScaleRunManifest."""
    return ScaleRunManifest(
        run_id=run_id,
        manifest_schema_version=ManifestSchemaVersion.V1.value,
        scale_profile=scale_profile,
        employee_count=employee_count,
        tenant_count=tenant_count,
        seed=seed,
        density_strategy=density_strategy,
        dataset_identity=dataset_identity,
        environment_fingerprint=environment_fingerprint,
        schema_revision=schema_revision,
        vcos_revision=vcos_revision,
        generator_revision=generator_revision,
        evidence_schema_version=evidence_schema_version,
        start_time=datetime.utcnow().isoformat(),
    )
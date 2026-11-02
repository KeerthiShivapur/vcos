"""Authoritative Scale Validation Entrypoint.

Single deterministic execution entrypoint for authoritative scale validation.
Reuses all existing 35-F infrastructure components.

Usage:
    python -m tests.scale.authoritative --profile 10k
    python -m tests.scale.authoritative --profile 10k --output-dir ./results
    python -m tests.scale.authoritative --profile 10k --dry-run
"""

import asyncio
import argparse
import os
import sys
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any

from tests.scale.postgres.environment import (
    ScaleExecutionEnvironment,
    ScaleExecutionEnvironmentFactory,
    ExternalPostgresEnvironment,
)
from tests.scale.postgres.postgres_resolver import PostgreSQLRuntimeResolver, PostgreSQLRuntimeType
from tests.scale.readiness import ScaleEnvironmentReadinessAssessor, assess_scale_readiness
from tests.scale.acceptance_evidence import ScaleAcceptanceEvidence, AcceptanceResult
from tests.scale.acceptance_firewall import AcceptanceFirewall, evaluate_acceptance
from tests.scale.scale_state import (
    ScaleRunStateMachine,
    ScaleRunStateStore,
    DatasetIdentity,
    ScaleRunOwnership,
    create_dataset_identity,
)
from tests.scale.run_manifest import ScaleRunManifest, create_scale_run_manifest
from tests.scale.postgres.scale_runner import ScaleRunner
from tests.scale.generators import UniversalScaleProfile, UNIVERSAL_SCALE_PROFILES, ScaleConfig
from tests.scale.tenant_isolation import TenantIsolationValidator, run_tenant_isolation_test
from tests.scale.promotion_gates import PromotionGateEngine, ScaleValidationResult, ScaleProfile


class AuthoritativeScaleExecutor:
    """Authoritative scale validation executor.
    
    Orchestrates the complete authoritative validation pipeline using
    existing 35-F infrastructure components.
    """
    
    def __init__(
        self,
        profile_name: str,
        output_dir: Optional[str] = None,
        db_url: Optional[str] = None,
        dry_run: bool = False,
    ):
        self.profile_name = profile_name
        self.output_dir = output_dir or os.path.join(os.getcwd(), "scale_results")
        self.db_url = db_url or os.environ.get("TEST_DATABASE_URL")
        self.dry_run = dry_run
        
        # Results
        self.run_id: Optional[str] = None
        self.evidence: Optional[Any] = None
        self.manifest: Optional[Any] = None
        self.final_result: Optional[Dict[str, Any]] = None
        
        # Components
        self.environment: Optional[Any] = None
        self.profile: Optional[Any] = None
        self._state_store = None
        self._state_machine = None
        self._promotion_engine = None
    
    async def execute(self) -> Dict[str, Any]:
        """Execute the complete authoritative validation pipeline."""
        
        # Phase 1: Profile resolution
        self.profile = self._resolve_profile()
        if not self.profile:
            return {"status": "INVALID", "reason": f"Unknown profile: {self.profile_name}"}
        
        # Phase 2: Environment resolution
        try:
            await self._resolve_environment()
        except RuntimeError as e:
            return {"status": "BLOCKED", "reason": str(e)}
        except Exception as e:
            return {"status": "BLOCKED", "reason": f"Environment resolution failed: {e}"}
        
        if not self.environment:
            return {"status": "BLOCKED", "reason": "No valid PostgreSQL environment"}
        
        # Phase 3: Preflight & Readiness
        readiness = await self._run_preflight_and_readiness()
        if readiness.is_blocked:
            return {"status": "BLOCKED", "reason": "Environment readiness failed", "readiness": readiness.to_dict()}
        
        # Phase 4: Dry run check
        if self.dry_run:
            # Dry run must never claim authoritative PASS
            dry_run_result = readiness.to_dict()
            dry_run_result["authoritative_pass"] = False
            dry_run_result["dry_run"] = True
            return {"status": "DRY_RUN_COMPLETE", "readiness": dry_run_result}
        
        # Phase 5: Initialize manifest
        self._initialize_manifest()
        
        # Phase 6: Run authoritative pipeline
        self.final_result = await self._run_authoritative_pipeline()
        
        return self.final_result
    
    def _resolve_profile(self) -> Optional[UniversalScaleProfile]:
        """Resolve scale profile from name."""
        if self.profile_name in UNIVERSAL_SCALE_PROFILES:
            return UNIVERSAL_SCALE_PROFILES[self.profile_name]
        
        # Try to construct from ScaleConfig using correct UniversalScaleProfile fields
        if self.profile_name in ["5", "50", "500", "5000", "10000", "25000", "50000"]:
            emp_count = int(self.profile_name)
            return UniversalScaleProfile(
                name=self.profile_name,
                employee_count=emp_count,
                dept_per_employee=0.1,
                team_per_dept=max(3, emp_count // 500),
                project_per_team=max(2, emp_count // 1000),
                task_per_project=max(5, emp_count // 10000),
            )
        return None
    
    async def _resolve_environment(self) -> None:
        """Resolve PostgreSQL environment."""
        
        if not self.db_url:
            # Try to auto-resolve
            resolver = PostgreSQLRuntimeResolver()
            runtime_type, runtime_info = await resolver.resolve_best_runtime()
            
            if not runtime_info.available:
                # Try external
                self.db_url = os.environ.get("TEST_DATABASE_URL")
                if not self.db_url:
                    raise RuntimeError("No PostgreSQL environment available")
                
                self.environment = ExternalPostgresEnvironment(self.db_url)
            else:
                # Use resolved runtime
                env_type_map = {
                    PostgreSQLRuntimeType.DOCKER: "container",
                    PostgreSQLRuntimeType.PODMAN: "container",
                    PostgreSQLRuntimeType.LOCAL_POSTGRES: "windows_native",
                    PostgreSQLRuntimeType.EXTERNAL_POSTGRES: "external",
                }
                env_type = env_type_map.get(runtime_type, "external")
                self.environment = ScaleExecutionEnvironmentFactory.create(env_type, self.db_url)
        else:
            # Use explicit db_url
            self.environment = ExternalPostgresEnvironment(self.db_url)
        
        # Initialize environment
        await self.environment.initialize()
        
        # Run preflight
        preflight_result = await self.environment.preflight()
        if not preflight_result.get("can_proceed", False):
            raise RuntimeError(f"Environment preflight failed: {preflight_result.get('errors', 'Unknown')}")
    
    async def _run_preflight_and_readiness(self):
        """Run environment preflight and readiness assessment."""
        from tests.scale.readiness import ScaleEnvironmentReadinessAssessor, assess_scale_readiness
        
        # Use the assessor
        assessor = ScaleEnvironmentReadinessAssessor(self.db_url)
        await assessor.initialize()
        try:
            readiness = await assessor.assess()
            return readiness
        finally:
            await assessor.close()
    
    def _initialize_manifest(self) -> None:
        """Initialize the run manifest."""
        self.run_id = str(uuid.uuid4())[:12]
        
        # Create dataset identity
        dataset_identity = {
            "vcos_revision": self._get_vcos_revision(),
            "schema_revision": "unknown",
            "generator_revision": "1.0",
            "scale_profile": self.profile_name,
            "employee_count": self.profile.employee_count,
            "tenant_count": 1,
            "seed": 42,
            "density_strategy": "standard",
            "environment_fingerprint": "pending",
        }
        
        # Create manifest
        self.manifest = create_scale_run_manifest(
            run_id=self.run_id,
            scale_profile=self.profile_name,
            employee_count=self.profile.employee_count,
            tenant_count=1,
            seed=42,
            density_strategy="standard",
            dataset_identity=dataset_identity,
            environment_fingerprint={},
            schema_revision="unknown",
            vcos_revision=self._get_vcos_revision(),
            generator_revision="1.0",
            evidence_schema_version="1.0",
        )
    
    async def _run_authoritative_pipeline(self) -> Dict[str, Any]:
        """Run the complete authoritative validation pipeline using ScaleRunner."""
        
        # Create ScaleRunner with our environment and profile
        runner = ScaleRunner(
            environment=self.environment,
            profile=self.profile,
            org_id=self.run_id,
            output_dir=self.output_dir,
        )
        
        # Run the authoritative pipeline
        result = await runner.run()
        
        # Get the evidence from the runner
        self.evidence = result
        
        # Update manifest with results
        self.manifest.end_time = datetime.utcnow().isoformat()
        if isinstance(result, dict):
            self.manifest.duration_seconds = result.get("duration_seconds", 0)
            self.manifest.acceptance_result = result.get("acceptance_result", "UNKNOWN")
            self.manifest.acceptance_reason = result.get("reason", "")
            
            # Try to get evidence artifact path
            if "evidence_path" in result:
                self.manifest.evidence_artifact_path = result["evidence_path"]
        
        # Compute manifest fingerprint
        self.manifest.compute_fingerprint()
        
        # Save manifest
        manifest_path = self.manifest.save("scale_manifests")
        
        return {
            "run_id": self.run_id,
            "profile": self.profile_name,
            "status": result.get("acceptance_result", "UNKNOWN"),
            "evidence": result,
            "manifest_path": manifest_path,
            "manifest_fingerprint": self.manifest.manifest_fingerprint,
        }
    
    def _get_vcos_revision(self) -> str:
        """Get VCOS git revision."""
        try:
            import subprocess
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True, text=True, timeout=5, cwd=os.getcwd()
            )
            if result.returncode == 0:
                return result.stdout.strip()[:12]
        except Exception:
            pass
        return "unknown"


async def run_authoritative_scale(
    profile: str,
    output_dir: Optional[str] = None,
    db_url: Optional[str] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Run authoritative scale validation."""
    executor = AuthoritativeScaleExecutor(
        profile_name=profile,
        output_dir=output_dir,
        db_url=db_url,
        dry_run=dry_run,
    )
    return await executor.execute()


def main():
    """CLI entrypoint for authoritative scale validation."""
    parser = argparse.ArgumentParser(
        description="VCOS Authoritative Scale Validation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m tests.scale.authoritative --profile 10k
  python -m tests.scale.authoritative --profile 10k --output-dir ./results
  python -m tests.scale.authoritative --profile 10k --dry-run
  python -m tests.scale.authoritative --profile 10k --db-url postgresql+asyncpg://user:pass@host:5432/db
        """
    )
    
    parser.add_argument(
        "--profile",
        required=True,
        help="Scale profile: 5, 50, 500, 5k, 10k, 25k, 50k, etc."
    )
    parser.add_argument(
        "--output-dir",
        help="Output directory for results",
        default=None,
    )
    parser.add_argument(
        "--db-url",
        help="PostgreSQL connection URL (overrides TEST_DATABASE_URL)",
        default=None,
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run preflight and readiness only, skip generation",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Verbose output",
    )
    
    args = parser.parse_args()
    
    # Run the validation
    try:
        result = asyncio.run(run_authoritative_scale(
            profile=args.profile,
            output_dir=args.output_dir,
            db_url=args.db_url,
            dry_run=args.dry_run,
        ))
        
        # Print result
        print(json.dumps(result, indent=2, default=str))
        
        # Exit with appropriate code
        status = result.get("status", "UNKNOWN")
        if status == "PASS":
            sys.exit(0)
        elif status in ("BLOCKED", "INVALID", "INCONCLUSIVE"):
            sys.exit(2)
        else:
            sys.exit(1)
            
    except KeyboardInterrupt:
        print("\nInterrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
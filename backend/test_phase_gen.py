import os
os.environ['TEST_DATABASE_URL'] = 'postgresql+asyncpg://postgres:postgres@localhost:5432/vcos_test'
os.environ['PATH'] += ';C:\\Program Files\\PostgreSQL\\18\\bin'

from tests.scale.postgres.scale_runner import ScaleRunner
from tests.scale.postgres.environment import ExternalPostgresEnvironment
from tests.scale.generators import UniversalScaleProfile, UNIVERSAL_SCALE_PROFILES
from tests.scale.scale_state import ScaleRunStateMachine, ScaleRunStateStore, DatasetIdentity, ScaleRunOwnership, create_dataset_identity
from tests.scale.run_manifest import ScaleRunManifest, create_scale_run_manifest
from tests.scale.acceptance_evidence import ScaleAcceptanceEvidence, create_acceptance_evidence
from tests.scale.acceptance_firewall import AcceptanceFirewall
from tests.scale.promotion_gates import PromotionGateEngine, ScaleValidationResult, ScaleProfile
import asyncio
import uuid
import time
from datetime import datetime

async def test():
    db_url = "postgresql+asyncpg://postgres:postgres@localhost:5432/vcos_test"
    env = ExternalPostgresEnvironment(db_url)
    await env.initialize()
    
    runner = ScaleRunner(
        environment=env,
        profile=UNIVERSAL_SCALE_PROFILES["startup"],
        org_id="test-org",
        output_dir="scale_results",
    )
    
    print("Running full run...")
    result = await runner.run()
    print(f"Result: {result}")

asyncio.run(test())
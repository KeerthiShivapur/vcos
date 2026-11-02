#!/usr/bin/env python
"""Baseline measurement script for onboarding performance.

Measures the current onboarding provisioning performance
before any optimizations are applied.
"""

import asyncio
import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parent))

# Set test environment
os.environ["DATABASE_URL"] = "postgresql+asyncpg://postgres:postgres@localhost:5432/vcos_test"
os.environ["VCOS_TEST_MODE"] = "0"
os.environ["REDIS_ENABLED"] = "false"
os.environ["RATE_LIMIT_ENABLED"] = "false"
os.environ["EMAIL_TRANSPORT"] = "console"
os.environ["AI_PROVIDER"] = "none"
os.environ["SECRET_KEY"] = "test-secret-key-not-for-production"
os.environ["APP_ENV"] = "test"

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select

from app.services.provisioning_service import provisioning_service
from app.services.provisioning_instrumentation import OnboardingBaseline
from app.models.organization import Organization


async def run_baseline_measurement():
    """Run the baseline measurement."""
    print("=" * 80)
    print("VCOS ONBOARDING BASELINE MEASUREMENT")
    print("=" * 80)
    print(f"Environment: PostgreSQL 18.2 on Windows")
    print(f"Database: vcos_test")
    print(f"VCOS_TEST_MODE: 0 (production mode)")
    print(f"Started at: {datetime.now(timezone.utc).isoformat()}")
    print("=" * 80)

    engine = create_async_engine(
        "postgresql+asyncpg://postgres:postgres@localhost:5432/vcos_test",
        echo=False,
    )

    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as db:
        # Verify database connection
        result = await db.execute(select(Organization).limit(1))
        print(f"Database connection verified")

        # Run baseline measurement
        baseline = OnboardingBaseline()
        
        print("\nRunning baseline measurement (5 iterations)...")
        print("-" * 80)
        
        results = await baseline.measure_onboarding(
            db=db,
            organization_name="VCOS Baseline Test Corp",
            domain=f"baseline-{uuid.uuid4().hex[:8]}",
            admin_email=f"admin@baseline-{uuid.uuid4().hex[:8]}.com",
            admin_name="Baseline Admin",
            plan_key="starter",
            iterations=5,
        )

        # Print results
        print("\n" + "=" * 80)
        print("BASELINE MEASUREMENT RESULTS")
        print("=" * 80)
        print(f"Total iterations: {results['iterations']}")
        print(f"Successful runs: {results['successful_runs']}")
        print(f"Failed runs: {results['failed_runs']}")
        
        if results['successful_runs'] > 0:
            print(f"\nDuration Statistics (successful runs):")
            print(f"  Median:   {results['median_duration_seconds']:.2f} seconds")
            print(f"  Average:  {results['avg_duration_seconds']:.2f} seconds")
            print(f"  Min:      {results['min_duration_seconds']:.2f} seconds")
            print(f"  Max:      {results['max_duration_seconds']:.2f} seconds")
            print(f"  P95:      {results['p95_duration_seconds']:.2f} seconds")
        
        print(f"\nDetailed Results:")
        for r in results['detailed_results']:
            status = "PASS" if r.get('success') else "FAIL"
            print(f"  Iteration {r['iteration']}: {r['duration_seconds']:.2f}s - {status} ({r['final_state']})")
            if 'error' in r:
                print(f"    Error: {r['error']}")

        # Save results to file
        output_file = Path(__file__).parent / "ONBOARDING_BASELINE_RESULTS.json"
        with open(output_file, "w") as f:
            json.dump(results, f, indent=2, default=str)
        
        print(f"\nResults saved to: {output_file}")
        
        # Check if target met
        if results.get('median_duration_seconds'):
            target = 120  # 2 minutes
            if results['median_duration_seconds'] <= target:
                print(f"\nTARGET MET: Median duration ({results['median_duration_seconds']:.2f}s) <= {target}s")
            else:
                print(f"\nTARGET NOT MET: Median duration ({results['median_duration_seconds']:.2f}s) > {target}s")
                print(f"   Need {(results['median_duration_seconds'] - target) / target * 100:.1f}% improvement")

    await engine.dispose()
    print("\nBaseline measurement complete.")


if __name__ == "__main__":
    asyncio.run(run_baseline_measurement())
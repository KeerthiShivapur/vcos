import os
os.environ['TEST_DATABASE_URL'] = 'postgresql+asyncpg://postgres:postgres@localhost:5432/vcos_test'
os.environ['PATH'] += ';C:\\Program Files\\PostgreSQL\\18\\bin'

from tests.scale.readiness import ScaleEnvironmentReadinessAssessor
import asyncio
import time

async def test():
    print("Creating assessor...")
    assessor = ScaleEnvironmentReadinessAssessor('postgresql+asyncpg://postgres:postgres@localhost:5432/vcos_test', 'localhost:5432/vcos_test')
    print("Assessor created")
    
    print("Initializing...")
    start = time.time()
    await assessor.initialize()
    print(f"Initialized in {time.time() - start:.2f}s")
    
    print("Running assess...")
    start = time.time()
    result = await assessor.assess()
    print(f"Assessed in {time.time() - start:.2f}s")
    print(f"State: {result.state.value}")
    print(f"Mandatory passed: {result.mandatory_checks_passed}/{result.mandatory_checks_total}")
    for check in result.checks:
        print(f"  {check.check.value}: {'PASS' if check.passed else 'FAIL'} - {check.error or check.warning or 'OK'}")

import asyncio
asyncio.run(test())
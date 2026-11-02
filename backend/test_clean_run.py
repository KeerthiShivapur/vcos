import os
os.environ['TEST_DATABASE_URL'] = 'postgresql+asyncpg://postgres:postgres@localhost:5432/vcos_test'
os.environ['PATH'] += ';C:\\Program Files\\PostgreSQL\\18\\bin'

from tests.scale.postgres.scale_runner import ScaleRunner
from tests.scale.postgres.environment import ExternalPostgresEnvironment
from tests.scale.generators import UNIVERSAL_SCALE_PROFILES
import asyncio
import traceback
import sys
import json

async def test():
    db_url = 'postgresql+asyncpg://postgres:postgres@localhost:5432/vcos_test'
    env = ExternalPostgresEnvironment(db_url)
    await env.initialize()
    
    from tests.scale.generators import UNIVERSAL_SCALE_PROFILES
    
    runner = ScaleRunner(
        environment=env,
        profile=UNIVERSAL_SCALE_PROFILES['startup'],
        org_id='test-org',
        output_dir='scale_results',
    )
    
    print('Running full run...', flush=True)
    try:
        result = await runner.run()
        print(f'Result keys: {list(result.keys())}')
        print(f'Result status: {result.get("status", "unknown")}')
        if 'evidence' in result:
            evidence = result['evidence']
            print(f'Status: {evidence.get("acceptance_result", "unknown")}')
            if 'mandatory_checks' in evidence:
                for check, passed in evidence.get('mandatory_checks', {}).items():
                    print(f'  {check}: {passed}')
            if 'acceptance_reason' in evidence:
                print(f'Acceptance reason: {evidence["acceptance_reason"]}')
    except Exception as e:
        print(f'Exception: {e}')
        traceback.print_exc()

asyncio.run(test())
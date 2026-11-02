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
        with open('result.json', 'w') as f:
            json.dump(result, f, indent=2, default=str)
        print('Result written to result.json', flush=True)
    except Exception as e:
        print(f'Exception: {e}', flush=True)
        traceback.print_exc()

asyncio.run(test())
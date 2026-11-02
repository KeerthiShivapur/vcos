import os
os.environ['TEST_DATABASE_URL'] = 'postgresql+asyncpg://postgres:postgres@localhost:5432/vcos_test'
os.environ['PATH'] += ';C:\\Program Files\\PostgreSQL\\18\\bin'

from tests.scale.postgres.scale_runner import ScaleRunner
from tests.scale.postgres.environment import ExternalPostgresEnvironment
from tests.scale.generators import UNIVERSAL_SCALE_PROFILES
import asyncio
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
    
    print('Running full run...')
    try:
        result = await runner.run()
        print(f'Result keys: {list(result.keys())}')
        print(json.dumps(result, indent=2, default=str))
    except Exception as e:
        print(f'Exception: {e}')
        import traceback
        traceback.print_exc()

import asyncio
import json
asyncio.run(test())
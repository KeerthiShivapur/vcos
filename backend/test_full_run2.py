import os
os.environ['TEST_DATABASE_URL'] = 'postgresql+asyncpg://postgres:postgres@localhost:5432/vcos_test'
os.environ['PATH'] += ';C:\\Program Files\\PostgreSQL\\18\\bin'

from tests.scale.postgres.scale_runner import ScaleRunner
from tests.scale.postgres.environment import ExternalPostgresEnvironment
from tests.scale.generators import UNIVERSAL_SCALE_PROFILES
import asyncio
import traceback

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
    
    print('Running full run with debug...')
    try:
        result = await runner.run()
        print(f'Result keys: {list(result.keys())}')
        print(f'Result: {result}')
    except Exception as e:
        print(f'Exception: {e}')
        import traceback
        traceback.print_exc()

asyncio.run(test())
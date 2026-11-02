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
    
    print('Running _phase_generation directly...')
    try:
        print('Initializing environment...')
        await runner._phase_environment_preflight()
        print('Preflight passed')
        
        print('Running schema initialization...')
        await runner._phase_schema_initialization()
        print('Schema init passed')
        
        print('Running _phase_generation...')
        await runner._phase_generation()
        print('Generation phase completed')
        
        # Check evidence
        if runner._evidence:
            print(f'Evidence generation: {runner._evidence.generation}')
            print(f'Mandatory checks: {runner._evidence.mandatory_checks}')
    except Exception as e:
        print(f'Exception: {e}')
        traceback.print_exc()

import asyncio
import traceback
asyncio.run(test())
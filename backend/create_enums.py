import asyncio
import asyncpg

async def create_enums():
    conn = await asyncpg.connect('postgresql://vcos:vcos@localhost:5432/vcos_test')
    await conn.execute('SET search_path TO public')
    # Verify search_path
    result = await conn.fetchval('SHOW search_path')
    print(f'search_path: {result}')
    
    # Create all enums manually
    enums = [
        ('twin_sync_state', "'synced', 'pending', 'stale', 'diverged', 'error'"),
        ('drift_severity', "'low', 'medium', 'high', 'critical'"),
        ('calibration_state', "'pending', 'running', 'completed', 'failed'"),
        ('optimization_state', "'idle', 'analyzing', 'applying', 'validating'"),
        ('learning_signal_type', "'pattern', 'anomaly', 'drift', 'improvement', 'regression'"),
        ('attention_priority', "'low', 'normal', 'high', 'critical'"),
        ('drift_type', "'schema', 'data', 'behavior', 'performance'"),
        ('twin_scope_type', "'global', 'organization', 'project', 'team'"),
        ('degradation_severity', "'low', 'medium', 'high', 'critical'"),
        ('degradation_state', "'detected', 'investigating', 'mitigating', 'resolved'"),
    ]
    
    for name, values in enums:
        try:
            await conn.execute(f'CREATE TYPE {name} AS ENUM ({values})')
            print(f'Created {name}')
        except asyncpg.exceptions.DuplicateObjectError:
            print(f'{name} already exists')
        except Exception as e:
            print(f'Error creating {name}: {e}')
    
    await conn.close()

asyncio.run(create_enums())
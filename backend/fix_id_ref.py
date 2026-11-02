with open('tests/acceptance/test_release_candidate_slice_2d.py', 'r') as f:
    content = f.read()

old = '''        for phase in phases:
            execution = await release_failure_recovery_service.advance_phase(
                db=pg_db_session,
                release_id=execution.id,
                new_phase=phase,
                actor_id="test-user",
            )'''

new = '''        for phase in phases:
            execution = await release_failure_recovery_service.advance_phase(
                db=pg_db_session,
                release_id=execution.deployment_id,
                new_phase=phase,
                actor_id="test-user",
            )'''

content = content.replace(old, new)

with open('tests/acceptance/test_release_candidate_slice_2d.py', 'w') as f:
    f.write(content)
print('Done')
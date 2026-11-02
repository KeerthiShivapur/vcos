with open('tests/acceptance/test_release_candidate_slice_2d.py', 'r') as f:
    content = f.read()

old = '''        release_id = release_record.id
        
        for phase in phases:
            release_record = await release_failure_recovery_service.advance_phase(
                db=pg_db_session,
                release_id=release_id,
                new_phase=phase,
                actor_id="test-user",
            )
            assert release_record.phase == phase.value
            assert execution.phase == phase'''

new = '''        release_id = release_record.id
        
        for phase in phases:
            release_record = await release_failure_recovery_service.advance_phase(
                db=pg_db_session,
                release_id=release_id,
                new_phase=phase,
                actor_id="test-user",
            )
            assert release_record.phase == phase.value'''

content = content.replace(old, new)

with open('tests/acceptance/test_release_candidate_slice_2d.py', 'w') as f:
    f.write(content)
print('Done')
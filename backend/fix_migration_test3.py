with open('tests/acceptance/test_release_candidate_slice_2c.py', 'r') as f:
    content = f.read()

# Fix the migration failure test - expire and re-fetch
old = '''        assert injection.failure_type == "migration"
        assert release.failure_type == "migration"
        
        # Expire and re-fetch release to get updated phase
        await pg_db_session.refresh(release)
        assert release.phase == ReleasePhase.MIGRATION_FAILED.value
        assert release.failure_injected is True'''

new = '''        assert injection.failure_type == "migration"
        assert release.failure_type == "migration"
        
        # Expire and re-fetch release to get updated phase
        await pg_db_session.expire(release, ['phase'])
        await pg_db_session.refresh(release)
        assert release.phase == ReleasePhase.MIGRATION_FAILED.value
        assert release.failure_injected is True'''

content = content.replace(old, new)

with open('tests/acceptance/test_release_candidate_slice_2c.py', 'w') as f:
    f.write(content)
print('Done')
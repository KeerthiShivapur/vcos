with open('tests/acceptance/test_release_candidate_slice_2c.py', 'r') as f:
    content = f.read()

# Fix the migration failure test - remove await from expire_all
old = '''        # Commit and re-fetch release to get updated phase
        await pg_db_session.commit()
        await pg_db_session.expire_all()
        release = await pg_db_session.get(ReleaseRecord, release.id)
        assert release.phase == ReleasePhase.MIGRATION_FAILED.value
        assert release.failure_injected is True'''

new = '''        # Commit and re-fetch release to get updated phase
        await pg_db_session.commit()
        pg_db_session.expire_all()
        release = await pg_db_session.get(ReleaseRecord, release.id)
        assert release.phase == ReleasePhase.MIGRATION_FAILED.value
        assert release.failure_injected is True'''

content = content.replace(old, new)

with open('tests/acceptance/test_release_candidate_slice_2c.py', 'w') as f:
    f.write(content)
print('Done')
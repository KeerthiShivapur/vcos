with open('tests/acceptance/test_release_candidate_slice_2c.py', 'r') as f:
    content = f.read()

# Fix the canonical integrity failure test - expect RECOVERY_REQUIRED
old = '''        assert injection.failure_type == "canonical_integrity"
        release = await pg_db_session.get(ReleaseRecord, release.id)
        assert release.phase == ReleasePhase.CANONICAL_INTEGRITY_FAILED.value'''

new = '''        assert injection.failure_type == "canonical_integrity"
        # The failure handler transitions to RECOVERY_REQUIRED for canonical integrity failures
        release = await pg_db_session.get(ReleaseRecord, release.id)
        assert release.phase == ReleasePhase.RECOVERY_REQUIRED.value'''

content = content.replace(old, new)

with open('tests/acceptance/test_release_candidate_slice_2c.py', 'w') as f:
    f.write(content)
print('Done')
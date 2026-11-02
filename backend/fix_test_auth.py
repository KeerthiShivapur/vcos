with open('tests/acceptance/test_release_candidate_slice_2b.py', 'r') as f:
    content = f.read()

# Fix the test_authorization_state_change to include required fields
old = '''        auth = CompanyAuthorization(
            organization_id=org.id,
            title="Budget Authorization",
            state="requested",
        )'''

new = '''        auth = CompanyAuthorization(
            organization_id=org.id,
            title="Budget Authorization",
            state="requested",
            authorization_type="full",
            scope_type="company",
            fingerprint="test-fp-1",
            valid_from=utcnow(),
        )'''

content = content.replace(old, new)

# Also fix the approval part
old2 = '''        # Approve
        auth.state = "approved"
        auth.approved_by = "user-1"
        await pg_db_session.commit()'''

new2 = '''        # Approve
        auth.state = "approved"
        auth.approved_by = "user-1"
        auth.approved_at = utcnow()
        auth.fingerprint = "test-fp-2"
        await pg_db_session.commit()'''

content = content.replace(old2, new2)

with open('tests/acceptance/test_release_candidate_slice_2b.py', 'w') as f:
    f.write(content)
print('Done')
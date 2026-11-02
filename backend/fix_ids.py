with open('tests/acceptance/test_release_candidate_slice_2a.py', 'r') as f:
    content = f.read()

# Fix all hardcoded IDs
replacements = [
    ('id="bkp-test001"', 'id=f"bkp-test-{uuid.uuid4().hex[:8]}"'),
    ('id="alt-orphan"', 'id=f"alt-orphan-{uuid.uuid4().hex[:8]}"'),
    ('id="comm-no-auth"', 'id=f"comm-no-auth-{uuid.uuid4().hex[:8]}"'),
    ('id="auth-bad-temp"', 'id=f"auth-bad-temp-{uuid.uuid4().hex[:8]}"'),
    ('id="auth-ungoverned"', 'id=f"auth-ungoverned-{uuid.uuid4().hex[:8]}"'),
    ('id="auth-org2"', 'id=f"auth-org2-{uuid.uuid4().hex[:8]}"'),
    ('id="comm-cross-tenant"', 'id=f"comm-cross-tenant-{uuid.uuid4().hex[:8]}"'),
    ('id="event-bad-temp"', 'id=f"event-bad-temp-{uuid.uuid4().hex[:8]}"'),
    ('id="auth-ungoverned-block"', 'id=f"auth-ungoverned-block-{uuid.uuid4().hex[:8]}"'),
    ('id="bkp-warning-test"', 'id=f"bkp-warning-test-{uuid.uuid4().hex[:8]}"'),
    ('id="op-stuck"', 'id=f"op-stuck-{uuid.uuid4().hex[:8]}"'),
    ('id="bkp-serialize"', 'id=f"bkp-serialize-{uuid.uuid4().hex[:8]}"'),
    ('id="bkp-org1"', 'id=f"bkp-org1-{uuid.uuid4().hex[:8]}"'),
    ('id="bkp-org2"', 'id=f"bkp-org2-{uuid.uuid4().hex[:8]}"'),
    ('id="alt-orphan"', 'id=f"alt-orphan-{uuid.uuid4().hex[:8]}"'),  # duplicate
]

for old, new in replacements:
    content = content.replace(old, new)

with open('tests/acceptance/test_release_candidate_slice_2a.py', 'w') as f:
    f.write(content)
print('Done')
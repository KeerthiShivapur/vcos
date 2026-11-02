with open('tests/acceptance/test_release_candidate_slice_2a.py', 'r') as f:
    content = f.read()

# Fix all hardcoded slugs
replacements = [
    ('slug="test-org-nobackup"', 'slug=f"test-org-nobackup-{uuid.uuid4().hex[:8]}"'),
    ('slug="test-org-bad"', 'slug=f"test-org-bad-{uuid.uuid4().hex[:8]}"'),
    ('slug="test-org-bad-prov"', 'slug=f"test-org-bad-prov-{uuid.uuid4().hex[:8]}"'),
    ('slug="test-org-bad-temp"', 'slug=f"test-org-bad-temp-{uuid.uuid4().hex[:8]}"'),
    ('slug="test-org-bad-gov"', 'slug=f"test-org-bad-gov-{uuid.uuid4().hex[:8]}"'),
    ('slug="tenant-a"', 'slug=f"tenant-a-{uuid.uuid4().hex[:8]}"'),
    ('slug="tenant-b"', 'slug=f"tenant-b-{uuid.uuid4().hex[:8]}"'),
    ('slug="test-org-bad-long"', 'slug=f"test-org-bad-long-{uuid.uuid4().hex[:8]}"'),
    ('slug="test-org-blocked"', 'slug=f"test-org-blocked-{uuid.uuid4().hex[:8]}"'),
    ('slug="test-org-warning"', 'slug=f"test-org-warning-{uuid.uuid4().hex[:8]}"'),
    ('slug="test-org-concurrency"', 'slug=f"test-org-concurrency-{uuid.uuid4().hex[:8]}"'),
    ('slug="test-org-serialize"', 'slug=f"test-org-serialize-{uuid.uuid4().hex[:8]}"'),
    ('slug="org-1"', 'slug=f"org-1-{uuid.uuid4().hex[:8]}"'),
    ('slug="org-2"', 'slug=f"org-2-{uuid.uuid4().hex[:8]}"'),
    ('slug="test-org-dr"', 'slug=f"test-org-dr-{uuid.uuid4().hex[:8]}"'),
    ('slug="test-org-obs"', 'slug=f"test-org-obs-{uuid.uuid4().hex[:8]}"'),
]

for old, new in replacements:
    content = content.replace(old, new)

with open('tests/acceptance/test_release_candidate_slice_2a.py', 'w') as f:
    f.write(content)
print('Done')
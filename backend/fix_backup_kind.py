with open('tests/acceptance/test_release_candidate_hardening_e2e.py', 'r') as f:
    content = f.read()

# Fix backup kind usage
content = content.replace('kind="FULL"', 'kind=BackupKind.FULL')
content = content.replace('kind="INCREMENTAL"', 'kind=BackupKind.INCREMENTAL')

with open('tests/acceptance/test_release_candidate_hardening_e2e.py', 'w') as f:
    f.write(content)
print('Done')
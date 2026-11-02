with open('tests/acceptance/test_backup_restore_roundtrip.py', 'r') as f:
    content = f.read()

# Fix the observation_type in _create_observations - change "internal_operation" to "external_operation"
content = content.replace(
    'observation_type="internal_operation",',
    'observation_type="external_operation",'
)

with open('tests/acceptance/test_backup_restore_roundtrip.py', 'w') as f:
    f.write(content)

print('Fixed observation_type')
with open('tests/acceptance/test_acceptance_real.py', 'r') as f:
    content = f.read()

# Fix SyncScaleGenerator call - add organization_id
content = content.replace(
    '''generator = SyncScaleGenerator(db_session, config)''',
    '''generator = SyncScaleGenerator(db_session, test_caller.organization_id, config)'''
)

with open('tests/acceptance/test_acceptance_real.py', 'w') as f:
    f.write(content)

print('Fixed SyncScaleGenerator call')
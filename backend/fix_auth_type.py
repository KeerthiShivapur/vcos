import codecs

with codecs.open('tests/acceptance/test_production_deployment_dr_e2e.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix authorization_type from 'budget' to 'full'
content = content.replace(
    'authorization_type="budget"',
    'authorization_type="full"'
)

# Also fix the second authorization (Post-Restore Budget)
content = content.replace(
    'authorization_type="budget"',
    'authorization_type="full"'
)

with codecs.open('tests/acceptance/test_production_deployment_dr_e2e.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Fixed authorization_type')
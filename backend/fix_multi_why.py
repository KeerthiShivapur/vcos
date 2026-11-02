import codecs

with codecs.open('tests/acceptance/test_production_deployment_dr_e2e.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix CompanyDecision why -> rationale in multi-tenant test
old = '''            why="Test decision for multi-tenant DR",'''
new = '''            rationale="Test decision for multi-tenant DR",'''

if old in content:
    content = content.replace(old, new)
    print('Fixed CompanyDecision why')
else:
    print('Not found')

with codecs.open('tests/acceptance/test_production_deployment_dr_e2e.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Done')
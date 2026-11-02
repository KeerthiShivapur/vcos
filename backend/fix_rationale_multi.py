import codecs

with codecs.open('tests/acceptance/test_production_deployment_dr_e2e.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix CompanyDecision why -> rationale in multi-tenant test
content = content.replace(
    'why="Org {i+1} Decision",',
    'rationale="Org {i+1} Decision",'
)

# Fix the second CompanyDecision
content = content.replace(
    'why="Verify company can make new decisions after restore",',
    'rationale="Verify company can make new decisions after restore",'
)

with codecs.open('tests/acceptance/test_production_deployment_dr_e2e.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Fixed rationale/why in multi-tenant test')
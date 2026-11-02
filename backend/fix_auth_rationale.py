import codecs

with codecs.open('tests/acceptance/test_production_deployment_dr_e2e.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix CompanyAuthorization - revert why back to rationale
content = content.replace(
    'why="Approve budget for platform modernization project",',
    'rationale="Approve budget for platform modernization project",'
)

# Fix Post-Restore Authorization
content = content.replace(
    'why="New budget after disaster recovery",',
    'rationale="New budget after disaster recovery",'
)

with codecs.open('tests/acceptance/test_production_deployment_dr_e2e.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Fixed CompanyAuthorization rationale')
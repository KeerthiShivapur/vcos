import codecs

with codecs.open('tests/acceptance/test_production_deployment_dr_e2e.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix CompanyDecision - revert why back to rationale
content = content.replace(
    'why="Adopt microservices for platform modernization",',
    'rationale="Adopt microservices for platform modernization",'
)

# Fix CompanyAction - ensure why is used
content = content.replace(
    'rationale="Implement API gateway for microservices",',
    'why="Implement API gateway for microservices",'
)

# Fix Post-Restore Action
content = content.replace(
    'rationale="New action after disaster recovery",',
    'why="New action after disaster recovery",'
)

with codecs.open('tests/acceptance/test_production_deployment_dr_e2e.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Fixed rationale/why')
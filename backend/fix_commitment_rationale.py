import codecs

with codecs.open('tests/acceptance/test_production_deployment_dr_e2e.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix CompanyCommitment - revert why back to rationale
content = content.replace(
    'why="Complete API v2 design and implementation",',
    'rationale="Complete API v2 design and implementation",'
)

# Fix Post-Restore Commitment
content = content.replace(
    'why="New commitment after disaster recovery",',
    'rationale="New commitment after disaster recovery",'
)

with codecs.open('tests/acceptance/test_production_deployment_dr_e2e.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Fixed CompanyCommitment rationale')
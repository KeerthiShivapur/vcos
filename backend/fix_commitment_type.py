import codecs

with codecs.open('tests/acceptance/test_production_deployment_dr_e2e.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix commitment_type from 'deliverable' to 'conditional'
content = content.replace(
    'commitment_type="deliverable"',
    'commitment_type="conditional"'
)

# Fix both occurrences
content = content.replace(
    'commitment_type="deliverable"',
    'commitment_type="conditional"'
)

with codecs.open('tests/acceptance/test_production_deployment_dr_e2e.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Fixed commitment_type')
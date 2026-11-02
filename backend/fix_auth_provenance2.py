import codecs

with codecs.open('tests/acceptance/test_production_deployment_dr_e2e.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix the authorization mutation to include policy_id in provenance
old_provenance = 'provenance={"decision_id": decision_id},'
new_provenance = 'provenance={"decision_id": decision_id, "policy_id": "default-policy"},'

content = content.replace(old_provenance, new_provenance)

with codecs.open('tests/acceptance/test_production_deployment_dr_e2e.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Fixed authorization provenance with policy_id')
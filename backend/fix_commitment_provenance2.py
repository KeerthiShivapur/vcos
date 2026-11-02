import codecs

with codecs.open('tests/acceptance/test_production_deployment_dr_e2e.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix the commitment provenance to include decision_id
old_provenance = 'provenance={"authorization_id": authorization_id, "source_company_decision_id": decision_id},'
new_provenance = 'provenance={"authorization_id": authorization_id, "decision_id": decision_id, "source_company_decision_id": decision_id},'

content = content.replace(old_provenance, new_provenance)

with codecs.open('tests/acceptance/test_production_deployment_dr_e2e.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Fixed commitment provenance with decision_id')
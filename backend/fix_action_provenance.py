import codecs

with codecs.open('tests/acceptance/test_production_deployment_dr_e2e.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Add source_commitment_id to action provenance
old_provenance = 'provenance={"source_company_decision_id": decision_id, "source_scenario_id": None},'
new_provenance = 'provenance={"source_company_decision_id": decision_id, "source_commitment_id": commitment_id, "source_scenario_id": None},'

content = content.replace(old_provenance, new_provenance)

with codecs.open('tests/acceptance/test_production_deployment_dr_e2e.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Fixed action provenance')
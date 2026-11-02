with open('tests/acceptance/test_release_candidate_slice_2b.py', 'r') as f:
    content = f.read()

# Add source_event_id to all CompanyDecision creations
old = 'decision = CompanyDecision(organization_id=org_a.id, decision_id="DEC-A-001", kind="strategic", title="A\'s Decision", state="proposed")'
new = 'decision = CompanyDecision(organization_id=org_a.id, decision_id="DEC-A-001", kind="strategic", title="A\'s Decision", state="proposed", source_event_id="evt-001")'

content = content.replace(old, new)

with open('tests/acceptance/test_release_candidate_slice_2b.py', 'w') as f:
    f.write(content)
print('Done')
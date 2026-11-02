with open('tests/acceptance/test_release_candidate_slice_2b.py', 'r') as f:
    content = f.read()

# Fix reverse_tenant_isolation - add source_event_id
old = 'decision = CompanyDecision(organization_id=org_b.id, decision_id="DEC-B-001", kind="strategic", title="B\'s Decision", state="proposed")'
new = 'decision = CompanyDecision(organization_id=org_b.id, decision_id="DEC-B-001", kind="strategic", title="B\'s Decision", state="proposed", source_event_id="evt-002")'

content = content.replace(old, new)

with open('tests/acceptance/test_release_candidate_slice_2b.py', 'w') as f:
    f.write(content)
print('Done')
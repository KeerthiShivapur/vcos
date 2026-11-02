with open('tests/acceptance/test_release_candidate_slice_2b.py', 'r') as f:
    content = f.read()

# Fix the test_decision_state_change - remove occurred_at
old = '''        decision = CompanyDecision(
            organization_id=org.id,
            decision_id="DEC-001",
            kind="strategic",
            title="Important Decision",
            state="proposed",
            source_event_id="evt-001",
            event_name="test_event",
            occurred_at=utcnow(),
        )'''

new = '''        decision = CompanyDecision(
            organization_id=org.id,
            decision_id="DEC-001",
            kind="strategic",
            title="Important Decision",
            state="proposed",
            source_event_id="evt-001",
            event_name="test_event",
        )'''

content = content.replace(old, new)

with open('tests/acceptance/test_release_candidate_slice_2b.py', 'w') as f:
    f.write(content)
print('Done')
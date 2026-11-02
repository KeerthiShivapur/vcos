with open('tests/acceptance/test_release_candidate_slice_2b.py', 'r') as f:
    content = f.read()

# Fix aggregate_changes_with_data - add kind and source_event_id to decision
old = '''        # Add a decision
        decision = CompanyDecision(
            organization_id=org.id,
            decision_id="DEC-001",
            kind="strategic",
            title="Test Decision",
            state="proposed",
            fingerprint=_gen_fp(),
        )'''

new = '''        # Add a decision
        decision = CompanyDecision(
            organization_id=org.id,
            decision_id="DEC-001",
            kind="strategic",
            title="Test Decision",
            state="proposed",
            source_event_id="evt-001",
        )'''

content = content.replace(old, new)

with open('tests/acceptance/test_release_candidate_slice_2b.py', 'w') as f:
    f.write(content)
print('Done')
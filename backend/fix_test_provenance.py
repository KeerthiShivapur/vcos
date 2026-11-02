with open('tests/test_gate6e_contradiction_preservation.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix the second transition in test_existing_contradiction_workflow_still_works to provide provenance
old = '''        result = await canonical_transition(
            db=db_session,
            caller=caller_a,
            entity_type="CompanyDecisionContradiction",
            entity_id=contradiction.id,
            new_state="resolved",
            required_permissions=["commitments:manage"],
        )'''

new = '''        result = await canonical_transition(
            db=db_session,
            caller=caller_a,
            entity_type="CompanyDecisionContradiction",
            entity_id=contradiction.id,
            new_state="resolved",
            required_permissions=["commitments:manage"],
            provenance={"decision_id": decision.id},
        )'''

content = content.replace(old, new)

with open('tests/test_gate6e_contradiction_preservation.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Fixed test to provide provenance for second transition')
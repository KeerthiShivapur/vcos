with open('tests/test_gate6e_contradiction_preservation.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Update test_existing_contradiction_workflow_still_works to provide provenance
old = '''        # Transition through valid states
        result = await canonical_transition(
            db=db_session,
            caller=caller_a,
            entity_type="CompanyDecisionContradiction",
            entity_id=contradiction.id,
            new_state="acknowledged",
            required_permissions=["commitments:manage"],
        )'''

new = '''        # Transition through valid states
        result = await canonical_transition(
            db=db_session,
            caller=caller_a,
            entity_type="CompanyDecisionContradiction",
            entity_id=contradiction.id,
            new_state="acknowledged",
            required_permissions=["commitments:manage"],
            provenance={"decision_id": decision.id},
        )'''

content = content.replace(old, new)

with open('tests/test_gate6e_contradiction_preservation.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Updated test_existing_contradiction_workflow_still_works')
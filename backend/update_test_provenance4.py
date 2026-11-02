with open('tests/test_gate6e_contradiction_preservation.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Update test_contradiction_cannot_reference_other_tenant_decision to provide provenance
old = '''        # Attempt to transition - should fail
        result = await canonical_transition(
            db=db_session,
            caller=caller_a,
            entity_type="CompanyDecisionContradiction",
            entity_id=contradiction.id,
            new_state="acknowledged",
            required_permissions=["commitments:manage"],
        )'''

new = '''        # Attempt to transition - should fail
        result = await canonical_transition(
            db=db_session,
            caller=caller_a,
            entity_type="CompanyDecisionContradiction",
            entity_id=contradiction.id,
            new_state="acknowledged",
            required_permissions=["commitments:manage"],
            provenance={"decision_id": decision_b.id},
        )'''

content = content.replace(old, new)

with open('tests/test_gate6e_contradiction_preservation.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Updated test_contradiction_cannot_reference_other_tenant_decision')
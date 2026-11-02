with open('tests/test_gate6e_contradiction_preservation.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Update test_contradiction_sides_cannot_be_modified_without_supersession to provide provenance
old = '''        # Attempt to modify side_a without supersession
        result = await canonical_update(
            db=db_session,
            caller=caller_a,
            entity_type="CompanyDecisionContradiction",
            entity_id=contradiction.id,
            updates={"side_a_json": {"claim": "modified A"}},
            required_permissions=["commitments:manage"],
        )'''

new = '''        # Attempt to modify side_a without supersession
        result = await canonical_update(
            db=db_session,
            caller=caller_a,
            entity_type="CompanyDecisionContradiction",
            entity_id=contradiction.id,
            updates={"side_a_json": {"claim": "modified A"}},
            required_permissions=["commitments:manage"],
            provenance={"decision_id": decision.id},
        )'''

content = content.replace(old, new)

with open('tests/test_gate6e_contradiction_preservation.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Updated test_contradiction_sides_cannot_be_modified_without_supersession')
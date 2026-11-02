with open('tests/test_gate6e_contradiction_preservation.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Update test_historical_contradiction_cannot_be_modified to provide provenance
old = '''        # Try to modify superseded contradiction
        result = await canonical_update(
            db=db_session,
            caller=caller_a,
            entity_type="CompanyDecisionContradiction",
            entity_id=contradiction.id,
            updates={"side_a_json": {"claim": "tampered"}},
            required_permissions=["commitments:manage"],
        )'''

new = '''        # Try to modify superseded contradiction
        result = await canonical_update(
            db=db_session,
            caller=caller_a,
            entity_type="CompanyDecisionContradiction",
            entity_id=contradiction.id,
            updates={"side_a_json": {"claim": "tampered"}},
            required_permissions=["commitments:manage"],
            provenance={"decision_id": "dec-hist-test"},
        )'''

content = content.replace(old, new)

with open('tests/test_gate6e_contradiction_preservation.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Updated test_historical_contradiction_cannot_be_modified')
with open('tests/test_gate6f_epistemic_integrity.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix the evidence test UPDATE call to include evidence_ids
old_update = '''        result = await canonical_update(
            db=db_session,
            caller=caller_a,
            entity_type="CompanyDecision",
            entity_id=decision.id,
            updates={"epistemic_status": EpistemicStatus.OBSERVED},
            provenance={
                "decision_id": decision.id,
                "direct_observation": True,
            },
            required_permissions=["decisions:manage"],
        )'''

new_update = '''        result = await canonical_update(
            db=db_session,
            caller=caller_a,
            entity_type="CompanyDecision",
            entity_id=decision.id,
            updates={"epistemic_status": EpistemicStatus.OBSERVED},
            provenance={
                "decision_id": decision.id,
                "direct_observation": True,
                "evidence_ids": ["ev-1"],  # Must preserve original provenance fields
            },
            required_permissions=["decisions:manage"],
        )'''

content = content.replace(old_update, new_update)

with open('tests/test_gate6f_epistemic_integrity.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Fixed evidence test UPDATE call')
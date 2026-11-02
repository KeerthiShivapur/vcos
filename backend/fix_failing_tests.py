with open('tests/test_gate6e_contradiction_preservation.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix test_contradiction_provenance_preserved to copy provenance fields
old = '''        # Supersede
        new_contra = CompanyDecisionContradiction(
            organization_id=test_org_a.id,
            decision_id=decision.id,
            contradiction_key="cx:new",
            side_a_json={"claim": "new A", "evidence": "ev3"},
            side_b_json={"claim": "new B", "evidence": "ev4"},
            status="open",
            source_event_id="evt-new",
            supersedes_id=contradiction.id,
        )'''

new = '''        # Supersede - copy provenance fields from original
        new_contra = CompanyDecisionContradiction(
            organization_id=test_org_a.id,
            decision_id=decision.id,
            contradiction_key="cx:new",
            side_a_json={"claim": "new A", "evidence": "ev3"},
            side_b_json={"claim": "new B", "evidence": "ev4"},
            status="open",
            source_event_id="evt-new",
            supersedes_id=contradiction.id,
            lesson_memory_id=contradiction.lesson_memory_id,
            precedent_decision_id=contradiction.precedent_decision_id,
        )'''

content = content.replace(old, new)

with open('tests/test_gate6e_contradiction_preservation.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Fixed test_contradiction_provenance_preserved')
with open('tests/test_gate6f_epistemic_integrity.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Fix line 789 - should be indented with 8 spaces
lines[788] = '        from app.models.governance import GovernanceScope\n'
lines[789] = '        from app.models.governance_scope import GovernanceScopeType\n'
lines[790] = '        from app.services.governance_service import governance_service\n'

with open('tests/test_gate6f_epistemic_integrity.py', 'w', encoding='utf-8') as f:
    f.writelines(lines)

print('Fixed import indentation')
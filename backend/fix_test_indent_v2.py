with open('tests/test_gate6f_epistemic_integrity.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Fix the governance test function - lines 761-768
# Line 761: '    async def test_promotion_requires_governance_permissions(\n'
# Line 765: '        self, db_session, test_org_a, caller_a, caller_limited\n'
# Line 766: '    ):\n'

# Fix line 761 (index 760) - should be 4 spaces
lines[760] = '    async def test_promotion_requires_governance_permissions(\n'
# Fix line 765 (index 764) - should be 8 spaces
lines[764] = '        self, db_session, test_org_a, caller_a, caller_limited\n'
# Fix line 766 (index 765) - should be 4 spaces
lines[765] = '    ):\n'

with open('tests/test_gate6f_epistemic_integrity.py', 'w', encoding='utf-8') as f:
    f.writelines(lines)

print('Fixed indentation')
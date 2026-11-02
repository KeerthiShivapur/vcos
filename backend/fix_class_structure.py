with open('tests/test_gate6f_epistemic_integrity.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# The issue is that TestContradictionIntegration class is not properly closed
# before TestGovernanceAuthorization class starts.
# Line 761 (index 760) is a method at 4 spaces, but it should be part of TestGovernanceAuthorization class.
# Line 762 is the class definition for TestGovernanceAuthorization.
# We need to add the class definition for TestGovernanceAuthorization before the method.

# Find the line with "class TestGovernanceAuthorization:" and fix the structure
# The issue is that lines 761-766 are the method, but they're not inside a class properly.
# The class TestGovernanceAuthorization starts at line 762 (index 761), but the method
# at line 761 is outside any class.

# We need to move the method inside the class. The class definition is at line 762 (index 761).
# The method should be inside the class (indented by 4 spaces).

# Let's rebuild the section properly
# Lines 760-766 (indices 759-765) need to be restructured

# Current structure (indices 759-765):
# 760: '\n' (blank line)
# 761: '    async def test_promotion_requires_governance_permissions(\n' (4 spaces - method inside class)
# 762: 'class TestGovernanceAuthorization:' (0 spaces - class definition)
# 763: '    """Test governance authorization for epistemic promotion."""' (4 spaces - class docstring)
# 764: '\n' (blank)
# 765: '        self, db_session, test_org_a, caller_a, caller_limited\n' (8 spaces - method params)
# 766: '    ):\n' (4 spaces - method def end)

# The issue: line 761 (method) is before the class definition at line 762.
# We need to move the method inside the class.

# Let's reconstruct this section properly
new_lines = lines[:760]  # Up to the blank line before the method

# Add the class definition
new_lines.extend([
    '\n',
    'class TestGovernanceAuthorization:\n',
    '    """Test governance authorization for epistemic promotion."""\n',
    '\n',
    '    @pytest.mark.asyncio\n',
    '    async def test_promotion_requires_governance_permissions(\n',
    '        self, db_session, test_org_a, caller_a, caller_limited\n',
    '    ):\n',
    '        """Strong epistemic promotions require governance permissions."""\n',
])

# Add the rest of the method body (from line 767 onwards)
# The method body starts at line 767 (index 766)
for i in range(766, len(lines)):
    new_lines.append(lines[i])

with open('tests/test_gate6f_epistemic_integrity.py', 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print('Fixed class structure')
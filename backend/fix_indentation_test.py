with open('tests/test_gate6f_epistemic_integrity.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Fix the duplicate @pytest.mark.asyncio and indentation
new_lines = []
i = 0
while i < len(lines):
    if i == 764:  # Line 765 (0-indexed 764) - duplicate @pytest.mark.asyncio
        # Skip the duplicate
        i += 1
        continue
    if i == 765:  # Line 766 - duplicate @pytest.mark.asyncio with wrong indent
        # Skip this duplicate
        i += 1
        continue
    if i == 766:  # Line 767 - the actual @pytest.mark.asyncio with wrong indent
        # Fix indentation - should be 4 spaces
        lines[i] = '    @pytest.mark.asyncio\n'
        i += 1
        continue
    if i == 767:  # Line 768 - async def with wrong indent
        # Fix indentation - should be 4 spaces
        lines[i] = '    async def test_promotion_requires_governance_permissions(\n'
        i += 1
        continue
    new_lines.append(lines[i])
    i += 1

with open('tests/test_gate6f_epistemic_integrity.py', 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print('Fixed indentation')
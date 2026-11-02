with open('tests/test_gate6f_epistemic_integrity.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Remove the duplicate @pytest.mark.asyncio line (index 765)
new_lines = lines[:765] + lines[766:]

with open('tests/test_gate6f_epistemic_integrity.py', 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print('Fixed duplicate decorator')
with open('tests/test_gate6f_epistemic_integrity.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Fix the incomplete line at index 836 (line 837)
# Line 837 (index 836) is '        )\n' - this is correct
# Line 836 (index 835) is the incomplete one

# Fix the incomplete line at index 835 (line 836)
lines[835] = '            assert "evidence:validate" in str(e).lower() or "permission" in str(e).lower()\n'
# Line 836 (index 836) is already '        )\n' - correct
# Line 837 (index 837) is '    \n' - correct
# Line 838 (index 838) is '    \n' - correct

# Ensure file ends with newline
if not lines[-1].endswith('\n'):
    lines[-1] = lines[-1] + '\n'

with open('tests/test_gate6f_epistemic_integrity.py', 'w', encoding='utf-8') as f:
    f.writelines(lines)

print('Fixed syntax error')
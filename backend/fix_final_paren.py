with open('tests/test_gate6f_epistemic_integrity.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Fix the incomplete line at index 836 (line 837)
lines[836] = '            assert "evidence:validate" in str(e).lower() or "permission" in str(e).lower()\n'
lines[836] = '        )\n'  # This replaces the same line
lines[837] = '    \n'
lines[838] = '    \n'

# Ensure file ends with newline
if not lines[-1].endswith('\n'):
    lines[-1] = lines[-1] + '\n'

with open('tests/test_gate6f_epistemic_integrity.py', 'w', encoding='utf-8') as f:
    f.writelines(lines)

print('Fixed syntax error')
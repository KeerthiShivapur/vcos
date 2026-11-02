with open('tests/test_gate6f_epistemic_integrity.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Fix the incomplete line at the end
lines[836] = '            assert "evidence:validate" in str(e).lower() or "permission" in str(e).lower()\n'
lines.append('        )\n')
lines.append('    \n')
lines.append('    \n')

with open('tests/test_gate6f_epistemic_integrity.py', 'w', encoding='utf-8') as f:
    f.writelines(lines)

print('Fixed incomplete file ending')
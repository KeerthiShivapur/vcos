with open('tests/test_gate6f_epistemic_integrity.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix the incomplete line
old = '            assert "evidence:validate" in str(e).lower() or "permission" in str('
new = '            assert "evidence:validate" in str(e).lower() or "permission" in str(e).lower()'

content = content.replace(old, new)

with open('tests/test_gate6f_epistemic_integrity.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Fixed')
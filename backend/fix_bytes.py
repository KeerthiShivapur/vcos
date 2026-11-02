with open('tests/test_gate6f_epistemic_integrity.py', 'rb') as f:
    content = f.read()

# Find and fix the problematic sequence
old = b'assert "evidence:validate" in str(e).lower() or "permission" in str('
new = b'assert "evidence:validate" in str(e).lower() or "permission" in str(e).lower()'

content = content.replace(old, new)

with open('tests/test_gate6f_epistemic_integrity.py', 'wb') as f:
    f.write(content)

print('Fixed')
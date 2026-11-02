with open('tests/test_gate6f_epistemic_integrity.py', 'rb') as f:
    content = f.read()

# Fix the extra closing paren
old = b'except Exception as e:\r\n            assert "evidence:validate" in str(e).lower() or "permission" in str(e).lower()\r\n        )'
new = b'except Exception as e:\r\n            assert "evidence:validate" in str(e).lower() or "permission" in str(e).lower()\r\n'

content = content.replace(old, new)

with open('tests/test_gate6f_epistemic_integrity.py', 'wb') as f:
    f.write(content)

print('Fixed extra closing paren')
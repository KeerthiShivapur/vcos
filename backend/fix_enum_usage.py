with open('tests/test_gate6f_epistemic_integrity.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix the GovernanceScopeType usage
content = content.replace('scope_type=GovernanceScopeType.PROJECT,', 'scope_type="project",')

with open('tests/test_gate6f_epistemic_integrity.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Fixed GovernanceScopeType usage')
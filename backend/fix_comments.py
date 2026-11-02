with open('app/intelligence/canonical_integration_service.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Fix lines 851-859 (indices 850-859) - these are comments that need # prefix
for i in range(850, 860):
    line = lines[i]
    stripped = line.strip()
    if stripped and not stripped.startswith('#') and not stripped.startswith('"""') and not stripped.startswith('def ') and not stripped.startswith('if ') and not stripped.startswith('for ') and stripped.startswith('        '):
        if not stripped.startswith('#'):
            lines[i] = '        # ' + line.lstrip()
            print(f'Fixed line {i+1}: {lines[i].strip()}')

with open('app/intelligence/canonical_integration_service.py', 'w', encoding='utf-8') as f:
    f.writelines(lines)
print('Fixed comment lines')
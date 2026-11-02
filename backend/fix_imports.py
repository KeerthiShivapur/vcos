with open('create_company_state.py', 'r') as f:
    content = f.read()

# Fix the imports - remove duplicates
lines = content.split('\n')
new_lines = []
seen_imports = set()
in_import_section = True

for line in lines:
    if line.startswith('from app.models.') or line.startswith('from app.') or line.startswith('import '):
        if line.strip() not in seen_imports:
            seen_imports.add(line.strip())
            new_lines.append(line)
    else:
        if in_import_section and not line.strip().startswith('#'):
            in_import_section = False
        new_lines.append(line)

content = '\n'.join(new_lines)

with open('create_company_state.py', 'w') as f:
    f.write(content)
print('Cleaned up imports')
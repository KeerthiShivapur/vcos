with open('app/intelligence/canonical_mutation.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix the import order - move from __future__ import annotations to the top
lines = content.split('\n')
new_lines = []
future_import_found = False
other_lines = []

for line in lines:
    if line.strip() == 'from __future__ import annotations':
        future_import_found = True
    else:
        other_lines.append(line)

if future_import_found:
    new_content = 'from __future__ import annotations\n' + '\n'.join(other_lines)
else:
    new_content = '\n'.join(other_lines)

# Add sys and traceback imports at the top after the future import
lines = new_content.split('\n')
new_lines = []
future_done = False
for line in lines:
    new_lines.append(line)
    if line.strip() == 'from __future__ import annotations' and not future_done:
        new_lines.append('import sys')
        new_lines.append('import traceback')
        future_done = True

# Add excepthook after imports
new_content = '\n'.join(new_lines)
# Add excepthook after imports
lines = new_content.split('\n')
new_lines = []
imports_done = False
for line in lines:
    new_lines.append(line)
    if line.strip() == 'from app.models.governance import ApprovalPolicy' and not imports_done:
        new_lines.append('')
        new_lines.append('import sys')
        new_lines.append('import traceback')
        new_lines.append('')
        new_lines.append('# Global exception handler for UnboundLocalError')
        new_lines.append('def _excepthook(exc_type, exc_value, exc_traceback):')
        new_lines.append('    if isinstance(exc_value, UnboundLocalError):')
        new_lines.append('        print("=" * 80)')
        new_lines.append('        print("UNBOUND LOCAL ERROR CAUGHT:")')
        new_lines.append('        traceback.print_exception(exc_type, exc_value, exc_traceback)')
        new_lines.append('        print("=" * 80)')
        new_lines.append('    sys.__excepthook__(exc_type, exc_value, exc_traceback)')
        new_lines.append('')
        new_lines.append('sys.excepthook = _excepthook')
        new_lines.append('')
        imports_done = True

new_content = '\n'.join(new_lines)

with open('app/intelligence/canonical_mutation.py', 'w', encoding='utf-8') as f:
    f.write(new_content)

print('Done')
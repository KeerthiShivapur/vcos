with open('app/intelligence/canonical_mutation.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Remove the sys.excepthook and traceback import
lines = content.split('\n')
new_lines = []
skip_until_imports = False
in_excepthook = False

for i, line in enumerate(lines):
    stripped = line.strip()
    
    # Skip the excepthook function and sys.excepthook assignment
    if 'def _excepthook' in line:
        in_excepthook = True
        continue
    if in_excepthook:
        if stripped == 'sys.excepthook = _excepthook':
            in_excepthook = False
            continue
        continue
    
    # Skip the traceback import
    if stripped == 'import traceback' and not 'from __future__' in line:
        continue
    
    # Skip the excepthook function definition and sys.excepthook assignment
    if 'def _excepthook' in line:
        in_excepthook = True
        continue
    if 'sys.excepthook = _excepthook' in line:
        continue
    if 'import sys' in line and 'import traceback' not in line and 'import sys' not in ''.join(new_lines[-3:]):
        # This is the second sys import (the one after traceback)
        continue
    if 'import traceback' in line and 'from __future__' not in ''.join(new_lines):
        continue
    if 'import sys' in line and 'sys.excepthook' in ''.join(new_lines[-5:]):
        continue
    
    new_lines.append(line)

# Also remove the traceback import if it's at the top
new_content = '\n'.join(new_lines)

# Clean up duplicate imports
lines = new_content.split('\n')
new_lines = []
seen_imports = set()
for line in lines:
    stripped = line.strip()
    if stripped.startswith('import ') or stripped.startswith('from '):
        if stripped in seen_imports:
            continue
        seen_imports.add(stripped)
    new_lines.append(line)

new_content = '\n'.join(new_lines)

with open('app/intelligence/canonical_mutation.py', 'w', encoding='utf-8') as f:
    f.write(new_content)

print('Done')
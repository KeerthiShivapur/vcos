with open('app/intelligence/canonical_mutation.py', 'rb') as f:
    content = f.read()

# Fix the specific lines around the type_map at line 1815
# The issue is wrong indentation levels
lines = content.split(b'\n')

# Fix lines 1815-1835 (0-indexed: 1814-1834)
# Line 1815 (index 1814): b'                            type_map = {' -> should be 12 spaces
# Line 1816-1830 (index 1815-1829): entries should be 20 spaces
# Line 1831 (index 1830): b'                    }' -> should be 12 spaces
# Line 1832 (index 1831): b'                    model = type_map.get(target_entity_type)' -> should be 12 spaces
# Line 1833 (index 1832): b'                    if model:' -> should be 12 spaces
# Line 1834 (index 1833): b'                        # Use database-level optimistic update' -> should be 16 spaces
# Line 1835 (index 1834): b'                        pass' -> should be 16 spaces
# Line 1836 (index 1835): b'                ' -> should be 12 spaces (empty line with 4 spaces)

# Fix line 1815 (index 1814)
if lines[1814].startswith(b'                            type_map = {'):
    lines[1814] = b'            type_map = {'

# Fix lines 1816-1829 (indices 1815-1828): entries should have 20 spaces
for i in range(1815, 1830):
    if i < len(lines):
        line = lines[i]
        if line.startswith(b'                        ') and not line.startswith(b'                    }'):
            # Has 24 spaces but should have 20
            lines[i] = b'                ' + line.lstrip()

# Fix line 1831 (index 1830): closing brace
if lines[1830].startswith(b'                    }'):
    lines[1830] = b'            }'

# Fix line 1832 (index 1831): model = type_map.get
if lines[1831].startswith(b'                    model = type_map.get'):
    lines[1831] = b'            model = type_map.get(target_entity_type)'

# Fix line 1833 (index 1832): if model:
if lines[1832].startswith(b'                    if model:'):
    lines[1832] = b'            if model:'

# Fix line 1834 (index 1833): comment
if lines[1833].startswith(b'                        # Use database-level optimistic update'):
    lines[1833] = b'                # Use database-level optimistic update'

# Fix line 1835 (index 1834): pass
if lines[1834].startswith(b'                        pass'):
    lines[1834] = b'                pass'

# Fix line 1836 (index 1835): empty line with wrong indent
if lines[1835].startswith(b'                '):
    lines[1835] = b'            '

# Write back
content = b'\n'.join(lines)
with open('app/intelligence/canonical_mutation.py', 'wb') as f:
    f.write(content)
print('Fixed line by line')
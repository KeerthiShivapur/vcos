with open('app/intelligence/canonical_mutation.py', 'rb') as f:
    lines = f.read().split(b'\n')

# Fix lines 1815-1837 (0-indexed: 1814-1836)
# Line 1815 (index 1814): '            type_map = {' -> should be 20 spaces
# Lines 1816-1830 (indices 1815-1830): dict entries should be 24 spaces
# Line 1831 (index 1830): '                    }' -> 20 spaces
# Line 1832 (index 1831): '                model = type_map.get(target_entity_type)' -> 20 spaces
# Line 1833 (index 1832): '                    if model:' -> 20 spaces
# Line 1835 (index 1834): '                        # Use database-level optimistic update' -> 24 spaces
# Line 1835 (index 1834): '                        pass' -> 24 spaces
# Line 1836 (index 1835): '                ' -> 16 spaces (empty line)
# Line 1837 (index 1836): '                result = await mutation_fn(db)' -> 16 spaces

# Fix line 1815 (index 1814): '            type_map = {' -> should be 20 spaces
if lines[1814].startswith(b'            type_map = {'):
    lines[1814] = b'                    type_map = {'

# Fix lines 1816-1830 (indices 1815-1830): dict entries should be 24 spaces
for i in range(1815, 1831):
    if i < len(lines):
        line = lines[i]
        if line.startswith(b'                    ') and not line.startswith(b'                    }'):
            lines[i] = b'                        ' + line.lstrip()

# Fix line 1831 (index 1830): '                    }' -> 20 spaces
if lines[1830].startswith(b'                    }'):
    lines[1830] = b'                    }'

# Fix line 1832 (index 1831): '                model = type_map.get(target_entity_type)' -> 20 spaces
if lines[1831].startswith(b'                model = type_map.get(target_entity_type)'):
    lines[1831] = b'                    model = type_map.get(target_entity_type)'

# Fix line 1833 (index 1832): '                    if model:' -> 20 spaces
if lines[1832].startswith(b'                    if model:'):
    lines[1832] = b'                    if model:'

# Fix line 1834 (index 1833): '                        # Use database-level optimistic update' -> 24 spaces
if lines[1833].startswith(b'                        # Use database-level optimistic update'):
    lines[1833] = b'                        # Use database-level optimistic update'

# Fix line 1835 (index 1834): '                        pass' -> 24 spaces
if lines[1834].startswith(b'                        pass'):
    lines[1834] = b'                        pass'

# Fix line 1836 (index 1835): '                ' -> 16 spaces
if lines[1835].startswith(b'                '):
    lines[1835] = b'                '

# Fix line 1837 (index 1836): '                result = await mutation_fn(db)' -> 16 spaces
if lines[1836].startswith(b'                result = await mutation_fn(db)'):
    lines[1836] = b'                result = await mutation_fn(db)'

content = b'\n'.join(lines)

with open('app/intelligence/canonical_mutation.py', 'wb') as f:
    f.write(b'\n'.join(lines))

print('Fixed')
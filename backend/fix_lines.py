with open('app/intelligence/canonical_mutation.py', 'rb') as f:
    lines = f.read().split(b'\n')

# Fix lines 1572-1591 (0-indexed: 1571-1591)
# Line 1572 (index 1571): b'type_map = {' -> should be 8 spaces
# Line 1587 (index 1586): b'    }' -> should be 8 spaces
# Lines 1588-1591 (indices 1587-1590): should be 8 spaces

# Fix line 1572 (index 1571): type_map = {
if lines[1571] == b'type_map = {':
    lines[1571] = b'        type_map = {'

# Fix line 1587 (index 1586): }
if lines[1586] == b'    }':
    lines[1586] = b'        }'

# Fix lines 1588-1591 (indices 1587-1590)
for i in range(1587, 1591):
    if lines[i].startswith(b'    ') and not lines[i].startswith(b'        '):
        # Has 4 spaces but not 8, add 4 more
        lines[i] = b'        ' + lines[i][4:]

with open('app/intelligence/canonical_mutation.py', 'wb') as f:
    f.write(b'\n'.join(lines))
print('Fixed line by line')
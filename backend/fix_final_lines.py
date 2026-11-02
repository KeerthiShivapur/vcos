with open('app/intelligence/canonical_mutation.py', 'rb') as f:
    content = f.read().replace(b'\r\n', b'\n').replace(b'\r', b'\n')

lines = content.split(b'\n')

# Fix lines 1572-1591 (0-indexed: 1571-1591)
# Line 1572 (index 1571): type_map = { -> should be 8 spaces
# Line 1587 (index 1586): } -> should be 8 spaces
# Lines 1588-1591 (indices 1587-1590): should be 8 spaces

# Fix line 1572 (index 1571): type_map = {
if lines[1571].strip() == b'type_map = {':
    lines[1571] = b'        type_map = {'

# Fix line 1587 (index 1586): }
if lines[1586].strip() == b'}':
    lines[1586] = b'        }'

# Fix lines 1588-1591 (indices 1587-1590): should be 8 spaces
for i in range(1587, 1591):
    if i < len(lines):
        stripped = lines[i].lstrip()
        if stripped and not lines[i].startswith(b'        '):
            lines[i] = b'        ' + stripped

# Rejoin with \n
content = b'\n'.join(lines)

with open('app/intelligence/canonical_mutation.py', 'wb') as f:
    f.write(content)
print('Fixed with stripped check')
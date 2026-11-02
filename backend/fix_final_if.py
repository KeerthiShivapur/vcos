with open('app/intelligence/canonical_mutation.py', 'rb') as f:
    content = f.read()

lines = content.split(b'\n')

# Fix line 1835 (index 1834): should be '                        pass' (24 spaces)
if lines[1834].startswith(b'                '):
    lines[1834] = b'                        pass'

# Remove the extra empty line at 1836 (index 1835)
if lines[1835].startswith(b'                '):
    del lines[1835]

# Ensure line 1837 (now index 1835 after deletion) is at correct indentation
if lines[1835].startswith(b'                result = await mutation_fn(db)'):
    lines[1835] = b'                result = await mutation_fn(db)'

content = b'\n'.join(lines)

with open('app/intelligence/canonical_mutation.py', 'wb') as f:
    f.write(content)
print('Fixed')
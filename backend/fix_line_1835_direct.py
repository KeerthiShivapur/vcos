with open('app/intelligence/canonical_mutation.py', 'rb') as f:
    lines = f.read().split(b'\n')

# Fix line 1835 (index 1834): should be '                        pass' (24 spaces)
# The line is currently empty with 16 spaces
if lines[1834].startswith(b'                ') and lines[1834].strip() == b'':
    lines[1834] = b'                        pass'

# Ensure line 1837 (index 1836) is at correct indentation
if lines[1836].strip() == b'result = await mutation_fn(db)' and lines[1836].startswith(b'                '):
    lines[1836] = b'                result = await mutation_fn(db)'

with open('app/intelligence/canonical_mutation.py', 'wb') as f:
    f.write(b'\n'.join(lines))
print('Fixed')
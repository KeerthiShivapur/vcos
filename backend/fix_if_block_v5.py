with open('app/intelligence/canonical_mutation.py', 'rb') as f:
    content = f.read()

lines = content.split(b'\n')

# Fix lines 1833-1838 (indices 1832-1837)
# Line 1833 (index 1832): b'                    if model:' - keep
# Line 1834 (index 1833): b'                        # Use database-level optimistic update' - keep
# Line 1835 (index 1834): b'                ' - should be '                        pass'
# Line 1836 (index 1835): b'                ' - remove or keep as empty
# Line 1837 (index 1835): b'                result = await mutation_fn(db)' - should be at 16 spaces

# Fix line 1835 (index 1834): add pass statement
if lines[1834].startswith(b'                '):
    lines[1834] = b'                        pass'

# Remove the extra empty line at 1836 (index 1835)
if lines[1835].startswith(b'                '):
    del lines[1835]

# Fix line 1837 (now index 1835 after deletion): result = await mutation_fn(db) should be at 16 spaces
if lines[1835].startswith(b'                result = await mutation_fn(db)'):
    lines[1835] = b'                result = await mutation_fn(db)'

content = b'\n'.join(lines)

with open('app/intelligence/canonical_mutation.py', 'wb') as f:
    f.write(content)
print('Fixed')
with open('app/intelligence/canonical_mutation.py', 'rb') as f:
    content = f.read()

# The issue is at line 1835 (0-indexed 1834): empty line with 16 spaces
# Should be: '                        pass' (24 spaces)
# And line 1837 (index 1836): '                result = await mutation_fn(db)' should be at 16 spaces

# Find the exact pattern and fix it
old = b'                    if model:\r\n                        # Use database-level optimistic update\r\n                \r\n                result = await mutation_fn(db)'

new = b'                    if model:\r\n                        # Use database-level optimistic update\r\n                        pass\r\n                result = await mutation_fn(db)'

content = content.replace(old, new)

with open('app/intelligence/canonical_mutation.py', 'wb') as f:
    f.write(content)
print('Fixed')
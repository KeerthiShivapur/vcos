with open('app/intelligence/canonical_mutation.py', 'rb') as f:
    content = f.read()

# Find and fix the specific pattern
old = b'                    if model:\r\n                        # Use database-level optimistic update\r\n                \r\n                result = await mutation_fn(db)'

new = b'                    if model:\r\n                        # Use database-level optimistic update\r\n                        pass\r\n                result = await mutation_fn(db)'

content = content.replace(old, new)

with open('app/intelligence/canonical_mutation.py', 'wb') as f:
    f.write(content)

print('Fixed')
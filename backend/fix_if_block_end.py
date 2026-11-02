with open('app/intelligence/canonical_mutation.py', 'rb') as f:
    content = f.read()

# Fix the empty line and pass statement after the if model: block
old = b'                    if model:\r\n                        # Use database-level optimistic update\r\n                    pass\r\n            \r\n                \r\n                result = await mutation_fn(db)'

new = b'                    if model:\r\n                        # Use database-level optimistic update\r\n                        pass\r\n                result = await mutation_fn(db)'

content = content.replace(old, new)

with open('app/intelligence/canonical_mutation.py', 'wb') as f:
    f.write(content)
print('Fixed')
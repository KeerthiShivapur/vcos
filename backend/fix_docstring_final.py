with open('app/intelligence/canonical_integration_service.py', 'rb') as f:
    content = f.read()

# The issue is at offset 35003: b'"""Get user\'s workspace person'
# The backslash before the single quote in the triple-quoted string breaks the string
# We need to remove the backslash

old = b'"""Get user\\\'s workspace'
new = b'"""Get user\'s workspace'

print('Old:', old)
print('New:', new)
print('Count:', content.count(old))

content = content.replace(old, new)
print('Replacements made:', content.count(old))

with open('app/intelligence/canonical_integration_service.py', 'wb') as f:
    f.write(content)
print('Fixed')
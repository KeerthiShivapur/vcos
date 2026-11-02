with open('app/intelligence/canonical_mutation.py', 'rb') as f:
    content = f.read()

# Fix the indentation around line 1832
old = b'                        "User": User,\r\n                    }\r\n                    model = type_map.get(target_entity_type)\r\n                    if model:'

new = b'                        "User": User,\r\n                    }\r\n                    model = type_map.get(target_entity_type)\r\n                    if model:'

content = content.replace(old, new)

with open('app/intelligence/canonical_mutation.py', 'wb') as f:
    f.write(content)
print('Fixed')
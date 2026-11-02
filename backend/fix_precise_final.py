with open('app/intelligence/canonical_mutation.py', 'rb') as f:
    content = f.read()

# Fix the specific lines with exact byte matching
# Line 1572 (0-indexed 1571): b'type_map = {\r' -> b'        type_map = {\r'
# Line 1587 (0-indexed 1586): b'    }\r' -> b'        }\r'

content = content.replace(
    b'type_map = {\r',
    b'        type_map = {\r'
)

content = content.replace(
    b'    }\r\n        model = type_map.get(entity_type)',
    b'        }\r\n        model = type_map.get(entity_type)'
)

with open('app/intelligence/canonical_mutation.py', 'wb') as f:
    f.write(content)

print('Fixed precise')
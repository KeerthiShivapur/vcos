with open('app/intelligence/canonical_mutation.py', 'rb') as f:
    content = f.read()

# The file got corrupted. Let me fix the specific corrupted area around line 1191
# The issue is "entity_        type_map = {" should be "entity_type_map = {"

content = content.replace(
    b'entity_        type_map = {',
    b'entity_type_map = {'
)

with open('app/intelligence/canonical_mutation.py', 'wb') as f:
    f.write(content)
print('Fixed corruption')
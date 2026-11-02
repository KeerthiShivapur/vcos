with open('app/intelligence/canonical_mutation.py', 'rb') as f:
    content = f.read()

# Fix the specific indentation issue at line 1815 (0-indexed 1814)
# The type_map = { should be indented by 24 spaces (inside the if block)
old = (
    b'                if mutation_type == MutationType.UPDATE and target_id and expected_version is not None:\r\n'
    b'                    # Load the model for the entity type\r\n'
    b'            type_map = {\r\n'
)

new = (
    b'                if mutation_type == MutationType.UPDATE and target_id and expected_version is not None:\r\n'
    b'                    # Load the model for the entity type\r\n'
    b'                    type_map = {\r\n'
)

content = content.replace(old, new)

with open('app/intelligence/canonical_mutation.py', 'wb') as f:
    f.write(content)
print('Fixed')
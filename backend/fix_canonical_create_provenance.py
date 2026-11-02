with open('app/intelligence/canonical_mutation.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix canonical_create to pass provenance to _create_entity
old = '''        mutation_fn=lambda db: _create_entity(db, entity),
        fingerprint=fingerprint,
        provenance=provenance,'''

new = '''        mutation_fn=lambda db: _create_entity(db, entity, provenance),
        fingerprint=fingerprint,
        provenance=provenance,'''

content = content.replace(old, new)

with open('app/intelligence/canonical_mutation.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Fixed canonical_create to pass provenance')
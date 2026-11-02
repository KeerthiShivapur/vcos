with open('app/intelligence/canonical_mutation.py', 'rb') as f:
    content = f.read()

# Add debug output to canonical_update
old = b'        result = await db.execute(update_stmt)\r\n        await db.flush()\r\n        \r\n        # Check rowcount to see if update succeeded'
new = b'        result = await db.execute(update_stmt)\r\n        await db.flush()\r\n        print(f"DEBUG: rowcount={result.rowcount}, entity_id={entity_id}, expected_version={expected_version}")\r\n        \r\n        # Check rowcount to see if update succeeded'

content = content.replace(old, new)

with open('app/intelligence/canonical_mutation.py', 'wb') as f:
    f.write(content)
print('Added debug output')
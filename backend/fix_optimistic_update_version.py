with open('app/intelligence/canonical_mutation.py', 'rb') as f:
    content = f.read()

# Fix _execute_optimistic_update - replace model.version + 1 with literal
old = b'.values(**update_values, version=model.version + 1)'
new = b'.values(**update_values, version=expected_version + 1)'
content = content.replace(old, new)

with open('app/intelligence/canonical_mutation.py', 'wb') as f:
    f.write(content)

print("Fixed _execute_optimistic_update version increment")
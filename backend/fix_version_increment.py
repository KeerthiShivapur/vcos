with open('app/intelligence/canonical_mutation.py', 'rb') as f:
    content = f.read()

# Fix the version increment - it should use expected_version + 1, not model.version + 1
content = content.replace(
    b'update_values["version"] = model.version + 1',
    b'update_values["version"] = expected_version + 1'
)

with open('app/intelligence/canonical_mutation.py', 'wb') as f:
    f.write(content)
print('Fixed version increment')
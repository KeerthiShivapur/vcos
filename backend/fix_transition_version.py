with open('app/intelligence/canonical_mutation.py', 'rb') as f:
    content = f.read()

# Fix canonical_transition - replace model.version + 1 with expected_version + 1
old = b'"version": model.version + 1,'
new = b'"version": expected_version + 1,'
content = content.replace(old, new)

# Also fix the update_values in canonical_transition - there may be multiple occurrences
# Check for model.version + 1 in update_values context
old2 = b'            "version": model.version + 1,'
new2 = b'            "version": expected_version + 1,'
content = content.replace(old2, new2)

with open('app/intelligence/canonical_mutation.py', 'wb') as f:
    f.write(content)

print("Fixed canonical_transition version increment")
with open('app/intelligence/canonical_integration_service.py', 'rb') as f:
    content = f.read()
# Fix the escaped single quote in docstring - replace the literal backslash-quote sequence
content = content.replace(b'user\\\'s', b"user's")
with open('app/intelligence/canonical_integration_service.py', 'wb') as f:
    f.write(content)
print('Fixed')
with open('app/intelligence/canonical_integration_service.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Remove trailing triple quotes
if content.endswith('"""'):
    content = content[:-3]
    with open('app/intelligence/canonical_integration_service.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print('Removed trailing triple quotes')
else:
    print('No trailing triple quotes found')
with open('app/intelligence/canonical_integration_service.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix the apostrophe issue - use double quotes for the string containing apostrophe
content = content.replace(
    '''"""Get user's workspace personalization settings."""''',
    '"""Get user\'s workspace personalization settings."""'
)

with open('app/intelligence/canonical_integration_service.py', 'w', encoding='utf-8') as f:
    f.write(content)
print('Fixed apostrophe')
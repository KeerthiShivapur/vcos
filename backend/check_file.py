with open('app/intelligence/canonical_integration_service.py', 'r', encoding='utf-8') as f:
    content = f.read()

print('File length:', len(content))
print('Triple quotes:', content.count('"""'))
print('First 500 chars:', content[:500])
print('Last 500 chars:', content[-500:])
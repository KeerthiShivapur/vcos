with open('app/intelligence/canonical_integration_service.py', 'rb') as f:
    content = f.read()

# Check for the pattern
print('Count of b"\\\\\'s":', content.count(b'\\\\\'s'))
print('Count of b"\\\\\\\\\'s":', content.count(b'\\\\\\\\\'s'))

# Try to find the exact pattern
idx = content.find(b'Get user')
if idx >= 0:
    chunk = content[idx:idx+50]
    print('Chunk hex:', content[idx:idx+40].hex())
    print('Bytes:', [hex(b) for b in content[idx+8:idx+20]])
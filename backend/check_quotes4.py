with open('app/intelligence/canonical_integration_service.py', 'rb') as f:
    content = f.read()

idx = content.find(b'"""Get user')
if idx >= 0:
    chunk = content[idx:idx+60]
    # Check first 3 bytes
    print('First 3 bytes == b\"\"\"\"?', chunk[:3] == b'"""')
    print('First 10 bytes hex:', chunk[:10].hex())
    print('First 10 bytes ascii:', chunk[:10])
    
    # Also check the end
    end_idx = content.find(b'"""', idx + 3)
    if end_idx >= 0:
        end_chunk = content[end_idx-3:end_idx+3]
        print('End quotes == b""""?', content[end_idx:end_idx+3] == b'"""')
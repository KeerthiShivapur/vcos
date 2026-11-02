with open('app/intelligence/canonical_integration_service.py', 'rb') as f:
    content = f.read()

idx = content.find(b'Get user')
if idx >= 0:
    chunk = content[idx:idx+80]
    print('Hex:', chunk.hex())
    print('ASCII:', chunk)
    
    # Find the closing triple quotes
    end_idx = content.find(b'"""', idx + 3)
    print('End idx:', end_idx)
    if end_idx >= 0:
        print('Bytes after closing:', content[end_idx:end_idx+10].hex())
        print('ASCII:', content[end_idx:end_idx+10])
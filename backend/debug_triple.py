with open('app/intelligence/canonical_integration_service.py', 'rb') as f:
    content = f.read()

idx = content.find(b'Get user')
if idx >= 0:
    print('Found at:', idx)
    chunk = content[idx:idx+100]
    print('Hex:', chunk.hex())
    print('ASCII:', chunk)
    
    # Find triple quotes
    triple_idx = content.find(b'"""', idx)
    print('First triple quote at:', triple_idx)
    end_triple = content.find(b'"""', triple_idx + 3)
    print('Closing triple quote at:', end_triple)
    if end_triple >= 0:
        print('After closing:', content[end_triple:end_triple+10])
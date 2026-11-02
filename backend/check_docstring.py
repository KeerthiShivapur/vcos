with open('app/intelligence/canonical_integration_service.py', 'rb') as f:
    content = f.read()

idx = content.find(b'Build deep link')
if idx >= 0:
    chunk = content[idx:idx+200]
    # Find the closing triple quotes
    end_idx = chunk.find(b'"""')
    if end_idx >= 0:
        print('Found closing triple quotes at offset:', end_idx)
        print('Context:', chunk[end_idx:end_idx+10])
    else:
        print('No closing triple quotes found in chunk')
        # Search in full content
        end_idx = content.find(b'"""', idx + 3)
        if end_idx >= 0:
            print('Found in full content at offset:', end_idx)
            print('Context:', content[end_idx-10:end_idx+3])
        else:
            print('No closing triple quotes in entire file!')
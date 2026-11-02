with open('app/intelligence/canonical_integration_service.py', 'rb') as f:
    content = f.read()

idx = content.find(b'Get user')
if idx >= 0:
    # Find the closing triple quotes
    end_idx = content.find(b'"""', idx + 3)
    if end_idx >= 0:
        # Check the bytes right after the closing triple quotes
        after = content[end_idx+3:end_idx+10]
        print('Bytes after closing triple quotes:', after.hex())
        print('Ascii:', after)
    else:
        print('No closing triple quotes found!')
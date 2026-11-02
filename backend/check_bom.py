with open('app/intelligence/cohort_builder.py', 'rb') as f:
    content = f.read()
    # Check first 10 bytes
    print('First 10 bytes:', repr(content[:20]))
    print('Starts with BOM:', content.startswith(b'\xef\xbb\xbf'))
    
    # Check if there's a zero-width space or other invisible char at start
    for i, b in enumerate(content[:10]):
        print(f'Byte {i}: {b} ({chr(b) if b < 128 else "?"})')
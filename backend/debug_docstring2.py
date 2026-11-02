with open('app/intelligence/canonical_integration_service.py', 'rb') as f:
    content = f.read()

idx = content.find(b'"""Process a game action and return new state.')
if idx >= 0:
    print('Found at:', idx)
    # Show context
    print('Context:', content[idx:idx+500].decode('utf-8', errors='replace'))
    
    # Find the docstring boundaries
    doc_start = content.find(b'"""', idx)
    print('Docstring starts at:', doc_start)
    
    doc_end = content.find(b'"""', idx + 3)
    print('First """ after start:', doc_end)
    
    if doc_end >= 0:
        after_doc = content[doc_end+3:doc_end+100]
        print('After docstring:', repr(after_doc[:100]))
    else:
        print('No closing """ found - DOCSTRING IS NOT CLOSED!')
        
    # Show the function structure
    lines = content[idx:idx+500].split(b'\n')
    for i, line in enumerate(lines[:30]):
        print(f'Line {i}: {line!r}')
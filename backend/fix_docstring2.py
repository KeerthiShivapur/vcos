with open('app/intelligence/canonical_integration_service.py', 'rb') as f:
    content = f.read()

# Find the unmatched docstring
idx = content.find(b'"""Process a game action and return new state.')
if idx >= 0:
    print('Found at:', idx)
    # The docstring starts here but never closes
    # Find where the function body starts (first line after docstring that's not part of docstring)
    # The docstring should end before the first line of code
    doc_start = content.find(b'"""', idx)
    print('Docstring starts at:', doc_start)
    
    # The docstring should end before the first line of code
    # Find the first line that's not part of the docstring
    search_start = idx + 3
    # Find the end of the docstring - it should be a """ on its own line or at end of line
    doc_end = content.find(b'"""', idx + 3)
    print('First """ after start:', doc_end)
    
    if doc_end >= 0:
        # The docstring is properly closed? Let's check what's after
        after_doc = content[doc_end+3:doc_end+100]
        print('After docstring:', after_doc)
    else:
        print('No closing """ found - DOCSTRING IS NOT CLOSED!')
        
    # The issue: the docstring is never closed
    # We need to add """ before the function body
    # Find where the function body starts (first non-docstring line)
    lines = content[idx:idx+500].split(b'\n')
    for i, line in enumerate(lines):
        print(f'Line {i}: {line}')
        if line.strip() and not line.strip().startswith(b'"""') and not line.strip().startswith(b' ') and not line.strip().startswith(b'\t'):
            if line.strip() and not line.strip().startswith(b'"""') and not line.strip().startswith(b'#'):
                print(f'Body starts at relative line {i}: {line}')
                break
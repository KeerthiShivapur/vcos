import codecs

with codecs.open('tests/acceptance/test_production_deployment_dr_e2e.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Find the test function start
idx = content.find('async def test_complete_production_dr_lifecycle')
if idx == -1:
    print('Test function not found')
else:
    # Find the docstring end
    docstring_start = content.find('"""', idx)
    docstring_end = content.find('"""', docstring_start + 3) + 3
    
    # Find the first code after docstring
    code_start = content.find('\n', docstring_end) + 1
    while code_start < len(content) and content[code_start].strip() == '':
        code_start = content.find('\n', code_start) + 1
    
    # Print the first 30 lines after docstring
    lines = content[docstring_end:docstring_end+2000].split('\n')
    for i, line in enumerate(lines[:50]):
        print(f'{i}: {line}')
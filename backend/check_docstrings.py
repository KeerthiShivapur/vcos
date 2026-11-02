with open('app/intelligence/canonical_integration_service.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Check each line for triple quotes
in_docstring = False
docstring_start = -1
for i, line in enumerate(lines, 1):
    if '"""' in line:
        count = line.count('"""')
        if count % 2 == 1:
            print(f'Line {i+1}: Odd number of triple quotes ({count}) - {repr(line)}')
            # Check if this line has both opening and closing
            if line.count('"""') == 1:
                print(f'  -> Single triple quote on line {_}')

# Also check for single quotes that might be mistaken
for i, line in enumerate(lines, 1):
    if "'''" in line:
        print(f'Line {i+1}: Triple single quotes - {repr(line)}')
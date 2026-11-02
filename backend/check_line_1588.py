with open('app/intelligence/canonical_mutation.py', 'rb') as f:
    content = f.read()

# Find line 1587 (0-indexed line 1587)
idx = 0
line_num = 0
while True:
    nl = content.find(b'\n', idx)
    if nl == -1:
        break
    line = content[idx:nl]
    if line_num == 1587:
        print(f'Line 1587: {repr(content[idx:nl+1])}')
        # Check for tabs
        if b'\t' in content[idx:nl]:
            print('TAB FOUND!')
        break
    idx = nl + 1
    line_num += 1
"
with open('app/services/isolated_restore.py', 'rb') as f:
    content = f.read()
lines = content.split(b'\r\n')
for i in range(700, 730):
    line = lines[i]
    indent = len(line) - len(line.lstrip())
    has_tab = b'\t' in line[:len(line) - len(line.lstrip())]
    print(f'Line {i+1}: indent={indent} has_tab={has_tab} repr={repr(line[:80])}')
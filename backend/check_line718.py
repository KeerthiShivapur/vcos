with open('app/services/isolated_restore.py', 'rb') as f:
    content = f.read()
lines = content.split(b'\r\n')
line = lines[717]
print('Line 718:', repr(line))
print('Length:', len(line))
for i, b in enumerate(line[:60]):
    ch = chr(b) if 32 <= b < 127 else '?'
    print(f'  [{i}] = {b} (0x{b:02x}) {chr(b) if 32 <= b < 127 else "?"}')
with open('app/services/canonical_reality_integrity_service.py', 'rb') as f:
    content = f.read()

idx = content.find(b'async def check_gate30_integrity(')
before = content[idx-30:idx]
print('Before (repr):', repr(before))

for i, c in enumerate(before):
    ch = chr(c) if 32 <= c < 127 else '?'
    print(f'  {i}: {c:02x} {ch}')

# Check line 1802 specifically
with open('app/services/canonical_reality_integrity_service.py', 'r') as f:
    lines = f.readlines()
    for i, line in enumerate(lines[1795:1810], 1796):
        print(f'{i}: {repr(line)}')
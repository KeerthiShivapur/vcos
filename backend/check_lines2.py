with open('app/intelligence/canonical_integration_service.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

for i, line in enumerate(lines[945:980], 946):
    if '"""' in line or "'''" in line:
        print(f'Line {i}: {repr(line)}')
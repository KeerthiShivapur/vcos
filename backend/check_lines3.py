with open('app/intelligence/canonical_integration_service.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

for i, line in enumerate(lines[945:980], 946):
    dq_count = line.count('"')
    sq_count = line.count("'")
    if dq_count >= 3 or sq_count >= 3:
        print(f'Line {i}: {repr(line)}')
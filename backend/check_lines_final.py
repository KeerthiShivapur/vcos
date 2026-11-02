with open('app/intelligence/canonical_integration_service.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

for i, line in enumerate(lines[945:980], 946):
    dq = line.count('"')
    sq = line.count("'")
    if dq >= 3 or sq >= 3:
        print('Line {}: {}'.format(i, repr(line)))
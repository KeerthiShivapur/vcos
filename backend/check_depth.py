with open('app/intelligence/canonical_integration_service.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

depth = 0
for i, line in enumerate(lines, 1):
    dq = line.count('"""')
    if dq > 0:
        print('Line {}: depth change {} - {}'.format(i, dq, repr(line.strip())))
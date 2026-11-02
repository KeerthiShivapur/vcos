with open('app/intelligence/canonical_integration_service.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

count = 0
for i, line in enumerate(lines[:971], 1):
    count += line.count('"""')
    if '"""' in line:
        print(f'{i}: {repr(line.strip())} - count: {count}')

print(f'Total triple quotes up to line 971: {count}')
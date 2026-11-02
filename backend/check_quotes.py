import re

with open('app/intelligence/canonical_integration_service.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Count triple double quotes
triple_double = content.count('"""')
triple_single = content.count("'''")
print(f'Triple double quotes: {triple_double}')
print(f'Triple single quotes: {triple_single}')
print(f'Triple double even: {triple_double % 2 == 0}')
print(f'Triple single even: {triple_single % 2 == 0}')

# Check the problematic area
lines = content.split('\n')
for i, line in enumerate(lines[968:975], 969):
    print(f'{i}: {repr(line)}')
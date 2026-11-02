import re

with open('app/intelligence/canonical_integration_service.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Count triple quotes
triple_double = content.count('"""')
triple_single = content.count("'''")
print(f'Triple double quotes: {triple_double}')
print(f'Triple single quotes: {triple_single}')
print(f'Triple double even: {triple_double % 2 == 0}')
print(f'Triple single even: {triple_single % 2 == 0}')

# Find all triple double quote positions
positions = [m.start() for m in re.finditer('"""', content)]
print('Triple double quote positions:', positions)
print('Count:', len(positions))

# Check around the problematic area
for pos in positions:
    if 34000 < pos < 36000:
        context = content[max(0,pos-30):pos+30]
        print(f'Offset {pos}: {context}')
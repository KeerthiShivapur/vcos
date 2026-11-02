import re

with open('app/intelligence/canonical_integration_service.py', 'rb') as f:
    content = f.read()

# Find all triple double quotes
positions = []
for m in re.finditer(b'"""', content):
    positions.append(m.start())

print('Triple double quote positions:', positions)
print('Count:', len(positions))

# Check the ones around line 971 (approximate offset 35000-36000)
for pos in positions:
    if 34000 < pos < 36000:
        context = content[max(0,pos-30):pos+30]
        print(f'Offset {pos}: {context}')
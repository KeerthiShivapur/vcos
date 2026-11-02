import re

with open('app/intelligence/canonical_integration_service.py', 'rb') as f:
    content = f.read()

# Find all triple double quotes in the region
positions = []
for m in re.finditer(b'"""', content):
    positions.append(m.start())

print('Triple double quote positions in region 9000-10000:')
for pos in positions:
    if 9000 < pos < 10000:
        context = content[max(0,pos-30):pos+30]
        print(f'  Offset {pos}: {context}')
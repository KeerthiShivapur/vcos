import re

with open('app/intelligence/canonical_integration_service.py', 'rb') as f:
    content = f.read()

# Find all triple single quotes
positions = []
for m in re.finditer(b"'''", content):
    positions.append(m.start())

print('Triple single quote positions:', positions)
print('Count:', len(positions))

for pos in positions:
    context = content[max(0,pos-30):pos+30]
    print(f'  Offset {pos}: {context}')
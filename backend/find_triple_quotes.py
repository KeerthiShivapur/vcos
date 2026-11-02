import re

with open('app/intelligence/canonical_integration_service.py', 'rb') as f:
    content = f.read()

# Find all triple double quotes
positions = []
for m in re.finditer(b'"""', content):
    positions.append(m.start())

print('Triple double quote positions:', positions)
print('Count:', len(positions))

# They should be in pairs (open/close)
for i, pos in enumerate(positions):
    context = content[max(0,pos-20):pos+20]
    print(f'  {i}: offset {pos} - {context}')
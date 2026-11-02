with open('app/intelligence/canonical_integration_service.py', 'rb') as f:
    content = f.read()

import re
positions = [m.start() for m in re.finditer(b'"""', content)]
print('Triple double quote count:', len(positions))

for i, pos in enumerate(positions):
    context = content[max(0,pos-30):pos+30]
    print(f'{i}: offset {pos} -> {context}')
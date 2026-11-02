with open('app/intelligence/canonical_integration_service.py', 'rb') as f:
    content = f.read()

import re
positions = [m.start() for m in re.finditer(b'"""', content)]
print('Triple double quote count:', len(positions))

# Check pairs
for i in range(0, len(positions), 2):
    if i + 1 < len(positions):
        start = positions[i]
        end = positions[i+1]
        context = content[start:positions[i+1]+3]
        print(f'Pair {i//2}: {start}-{positions[i+1]} len={positions[i+1]-start}')
    else:
        print(f'UNMATCHED at {positions[i]}')
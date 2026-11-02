with open('app/intelligence/canonical_integration_service.py', 'rb') as f:
    content = f.read()

import re
positions = [m.start() for m in re.finditer(b'"""', content)]
print('Triple double quotes:', len(positions))

for i in range(0, len(positions), 2):
    if i+1 >= len(positions):
        print('UNMATCHED at index', i, 'offset', positions[i])
        break
    start = positions[i]
    end = positions[i+1]
    diff = positions[i+1] - positions[i]
    if diff > 5000:
        print('Large gap at pair', i//2, ':', positions[i], '->', positions[i+1], 'diff=', positions[i+1]-positions[i])
        context = content[max(0,start-50):start+50]
        print('Context:', content[max(0,start-50):start+50].decode('utf-8', errors='replace'))
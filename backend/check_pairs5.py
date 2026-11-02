with open('app/intelligence/canonical_integration_service.py', 'rb') as f:
    content = f.read()

import re
positions = [m.start() for m in re.finditer(b'"""', content)]
print('Triple double quotes:', len(positions))

# Check pairs properly
unmatched = []
for i in range(0, len(positions), 2):
    if i+1 >= len(positions):
        print(f'UNMATCHED at index {i}: offset {positions[i]}')
        # Show context
        pos = positions[i]
        context = content[max(0,pos-50):pos+50]
        print('Context:', content[max(0,pos-50):pos+50])
        break
    start = positions[i]
    end = positions[i+1]
    diff = positions[i+1] - positions[i]
    if diff > 5000:
        print(f'Large gap at pair {i//2}: {positions[i]} -> {positions[i+1]} (diff={diff})')
        context = content[max(0,positions[i]-50):positions[i]+50]
        print('Context:', content[max(0,positions[i]-50):positions[i]+50])
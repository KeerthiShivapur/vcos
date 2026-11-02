with open('app/intelligence/canonical_integration_service.py', 'rb') as f:
    content = f.read()

import re
positions = [m.start() for m in re.finditer(b'"""', content)]
print('Triple double quotes:', len(positions))
print('Even:', len(positions) % 2 == 0)

# Check if even
if len(positions) % 2 != 0:
    print('UNEVEN - there is an unmatched triple quote!')
    # Find which one is causing issues by checking pairs
    for i in range(0, len(positions)-1, 2):
        if i+1 >= len(positions):
            print(f'UNMATCHED at index {i}: offset {positions[i]}')
            break
        start = positions[i]
        end = positions[i+1]
        # Check if this pair makes sense (should be a docstring)
        if positions[i+1] - positions[i] > 10000:
            print(f'Large gap at pair {i//2}: {positions[i]} -> {positions[i+1]} (diff={positions[i+1]-positions[i]})')
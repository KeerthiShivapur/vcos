#!/usr/bin/env python3
"""Remove fingerprint=... from create_operation calls only."""

import re

with open('tests/test_gate32_canonical_reliability.py', 'r') as f:
    content = f.read()

# We'll parse the content and remove fingerprint=... only within create_operation calls
# This is a bit tricky - let's use a state machine approach

lines = content.split('\n')
new_lines = []
in_create_operation = False
paren_depth = 0

for i, line in enumerate(lines):
    # Check if we're entering a create_operation call
    if 'create_operation(' in line:
        in_create_operation = True
        paren_depth = line.count('(') - line.count(')')
    elif in_create_operation:
        paren_depth += line.count('(') - line.count(')')
        if paren_depth <= 0:
            in_create_operation = False
    
    # If we're in a create_operation call and line has fingerprint= with comma
    if in_create_operation and 'fingerprint=' in line:
        # Only remove if it's a keyword argument (starts with whitespace or comma)
        # Pattern: fingerprint="...", (with comma)
        new_line = re.sub(r'(^|\s)fingerprint="[^"]*",\s*', '', line)
        if new_line != line:
            print(f'Fixed line {i+1}: {line.rstrip()} -> {new_line.rstrip()}')
            line = new_line
    
    new_lines.append(line)

# Join and write
with open('tests/test_gate32_canonical_reliability.py', 'w') as f:
    f.write('\n'.join(new_lines))

print('Done')
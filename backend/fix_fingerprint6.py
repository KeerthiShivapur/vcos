#!/usr/bin/env python3
"""Carefully remove fingerprint=... from create_operation calls only."""

import re

with open('tests/test_gate32_canonical_reliability.py', 'r') as f:
    lines = f.readlines()

new_lines = []
in_create_operation = False
paren_depth = 0
fixed_count = 0

for i, line in enumerate(lines):
    # Track if we're in a create_operation call
    if 'create_operation(' in line:
        in_create_operation = True
        paren_depth = line.count('(') - line.count(')')
    
    if in_create_operation:
        paren_depth += line.count('(') - line.count(')')
        if paren_depth <= 0:
            in_create_operation = False
    
    # If we're in a create_operation call and line has fingerprint= with comma
    if in_create_operation and 'fingerprint=' in line:
        # Only remove if it's a keyword argument (not in a string)
        # Pattern: fingerprint="...", (with comma)
        # Use regex to match the whole keyword argument
        new_line = re.sub(r'(^|\s)fingerprint="[^"]*",\s*', '', line)
        if new_line != line:
            print(f'Fixed line {i+1}: {line.rstrip()} -> {new_line.rstrip()}')
            line = new_line
            fixed_count += 1
    
    new_lines.append(line)

print(f'Fixed {fixed_count} lines')

with open('tests/test_gate32_canonical_reliability.py', 'w') as f:
    f.writelines(new_lines)

print('Done')
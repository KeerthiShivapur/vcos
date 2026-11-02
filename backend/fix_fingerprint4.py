#!/usr/bin/env python3
"""Fix fingerprint params in test file - careful version."""

import re

with open('tests/test_gate32_canonical_reliability.py', 'r') as f:
    content = f.read()

# Strategy: Find all create_operation calls and remove fingerprint=... from them
# We need to be very careful - only remove fingerprint=... when it's a keyword arg in create_operation

# First, let's find all create_operation calls and their spans
# We'll do a more careful approach - process line by line

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
        # Count parentheses to track depth
        paren_depth = line.count('(') - line.count(')')
    else:
        in_create_operation = False
    
    if in_create_operation:
        paren_depth += line.count('(') - line.count(')')
        if paren_depth <= 0:
            in_create_operation = False
    
    # If we're in a create_operation call and line has fingerprint= with comma
    if in_create_operation and 'fingerprint=' in line:
        # Only remove if it's a keyword argument (not in a string)
        # Pattern: fingerprint="...", (with comma and optional whitespace)
        # But be careful not to break strings
        # Only remove if it looks like a keyword arg
        new_line = line
        # Pattern: fingerprint="...", (with comma and optional whitespace)
        # Only at the start of the line or after whitespace/comma
        new_line = re.sub(r'(^|\s)fingerprint="[^"]*",\s*', '', line)
        if new_line != line:
            print(f'Fixed line {i+1}: {line.rstrip()} -> {new_line.rstrip()}')
            line = new_line
            fixed_count += 1
    
    new_lines.append(line)

print(f'Fixed {fixed_count} lines')

with open('tests/test_gate32_canonical_reliability.py', 'w') as f:
    f.writelines(lines)

print('Done')
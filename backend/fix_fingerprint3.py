import re

with open('tests/test_gate32_canonical_reliability.py', 'r') as f:
    lines = f.readlines()

new_lines = []
in_create_operation = False
paren_depth = 0

for line in lines:
    stripped = line.strip()
    
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
        # Pattern: fingerprint="...", 
        import re
        new_line = re.sub(r'fingerprint="[^"]*",\s*', '', line)
        if new_line != line:
            print(f'Fixed: {line.rstrip()} -> {new_line.rstrip()}')
            line = new_line
    
    print(line.rstrip())

with open('tests/test_gate32_canonical_reliability.py', 'w') as f:
    for line in lines:
        f.write(line)
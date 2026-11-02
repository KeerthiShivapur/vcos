with open('tests/acceptance/adapters.py', 'r') as f:
    lines = f.readlines()

# Fix line 933 (index 932) - docstring should be 12 spaces
lines[932] = '            """Create outcomes from commitments."""\n'

with open('tests/acceptance/adapters.py', 'w') as f:
    f.writelines(lines)

print('Fixed')
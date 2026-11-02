with open('app/intelligence/canonical_integration_service.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Fix line 1473 (index 1472) - replace triple-quoted docstring with single-quoted string
old = lines[1472]
print('Before:', repr(lines[1472]))

lines[1472] = "    'Process a game action and return new state.'\n"

with open('app/intelligence/canonical_integration_service.py', 'w', encoding='utf-8') as f:
    f.writelines(lines)
print('Fixed')
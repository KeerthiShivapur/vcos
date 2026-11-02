with open('app/intelligence/canonical_integration_service.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Line 971 is index 970
old = lines[970]
print('Before:', repr(lines[970]))

# Replace with single-quoted string to avoid triple-quote issues
lines[970] = '        \'Get user\'s workspace personalization settings.\'\n'

print('Fixed line 971')

with open('app/intelligence/canonical_integration_service.py', 'w', encoding='utf-8') as f:
    f.writelines(lines)
print('Fixed')
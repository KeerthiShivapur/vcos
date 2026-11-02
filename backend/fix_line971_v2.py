with open('app/intelligence/canonical_integration_service.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Fix line 971 (index 970)
old_line = lines[970]
print('Before:', repr(lines[970]))

# Replace the entire line with a clean version
new_line = '        """Get user\'s workspace personalization settings."""\n'
lines[970] = new_line

with open('app/intelligence/canonical_integration_service.py', 'w', encoding='utf-8') as f:
    f.writelines(lines)
print('Fixed')
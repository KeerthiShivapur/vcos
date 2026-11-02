with open('app/intelligence/canonical_integration_service.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Fix line 971 (index 970)
# The issue: """Get user\'s workspace... with escaped quote
# In triple-quoted strings, don't escape single quotes

line_971 = lines[970]
print('Before:', repr(lines[970]))

if "user\\'s" in lines[970]:
    lines[970] = lines[970].replace("user\\'s", "user's")
    print('Fixed line 971')

with open('app/intelligence/canonical_integration_service.py', 'w', encoding='utf-8') as f:
    f.writelines(lines)
print('Fixed')
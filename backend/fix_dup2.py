with open('app/intelligence/canonical_mutation.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Remove lines 726-735 (0-indexed: 725-734)
# These are the duplicated code lines
new_lines = lines[:725] + lines[736:]

with open('app/intelligence/canonical_mutation.py', 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print('Removed lines 726-735')
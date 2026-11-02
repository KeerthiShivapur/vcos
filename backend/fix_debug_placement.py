with open('app/intelligence/canonical_mutation.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Remove the print from inside the docstring (line 667)
# The docstring ends at line 677 (0-indexed: 676)
# Insert the print after the docstring

# First, remove the line with the print in the docstring
# Line 667 (0-indexed: 666) has the print in the docstring
if 'print(f"DEBUG validate_contradiction_preservation ENTRY' in lines[666]:
    lines.pop(666)

# Now insert the print after the docstring (after line 677, which is now 676 since we removed one)
# Find the docstring end
for i, line in enumerate(lines):
    if i > 660 and '"""' in line and 'Validate that contradiction' not in line:
        docstring_end = i
        break

# Insert after the docstring
lines.insert(docstring_end + 1, '    print(f"DEBUG validate_contradiction_preservation ENTRY: target_entity_type={context.target_entity_type}, target_id={context.target_id}, mutation_type={context.mutation_type}")\n')

with open('app/intelligence/canonical_mutation.py', 'w', encoding='utf-8') as f:
    f.writelines(lines)

print('Fixed debug print placement')
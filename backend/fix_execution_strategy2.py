with open('app/models/execution_strategy.py', 'r') as f:
    lines = f.readlines()

# Fix: Remove extra ')' at line 1195 (index 1194)
# Insert RESPONSIBILITY_TYPES constant before RESPONSIBILITY_SCOPES

# Find the RESPONSIBILITY_SCOPES line
insert_idx = None
for i, line in enumerate(lines):
    if 'RESPONSIBILITY_SCOPES = (' in line:
        insert_idx = i
        break

if insert_idx is None:
    print("ERROR: Could not find RESPONSIBILITY_SCOPES = (")
else:
    # Remove extra ')' at index 1194 (0-based)
    # Based on the current file structure, the extra ')' is at index 1194
    # Let's find it by looking for a line that's just ')\n' after ASSESSMENT_VERDICTS
    extra_paren_idx = None
    for i in range(1190, 1210):
        if lines[i].strip() == ')' and i > 1190:
            # Check if previous line is 'inconclusive'
            if i > 0 and 'inconclusive' in lines[i-1]:
                extra_paren_idx = i
                break

    if extra_paren_idx is not None:
        print(f"Removing extra ')' at index {extra_paren_idx}")
        del lines[extra_paren_idx]
        insert_idx -= 1  # Adjust insert index
    else:
        print("Could not find extra ')'")

    # Insert RESPONSIBILITY_TYPES before RESPONSIBILITY_SCOPES
    responsibility_types = [
        '\n',
        'RESPONSIBILITY_TYPES = (\n',
        '    "accountability",\n',
        '    "ownership",\n',
        '    "approval",\n',
        '    "consultation",\n',
        '    "information",\n',
        ')\n',
        '\n',
    ]

    for i, item in enumerate([
        '\n',
        'RESPONSIBILITY_TYPES = (\n',
        '    "accountability",\n',
        '    "ownership",\n',
        '    "approval",\n',
        '    "consultation",\n',
        '    "information",\n',
        ')\n',
        '\n',
    ]):
        lines.insert(insert_idx + i, item)

with open('app/models/execution_strategy.py', 'w') as f:
    f.writelines(lines)

print('Fixed')
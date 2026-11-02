with open('app/models/execution_strategy.py', 'r') as f:
    lines = f.readlines()

# The orphaned items are at lines 1195-1199 (indices 1194-1198)
# RESPONSIBILITY_TYPES = ( is at line 1202 (index 1201)
# We need to remove lines 1195-1199 (indices 1194-1198) and insert them after line 1202 (index 1201)

# First, save the orphaned items
orphaned_items = lines[1194:1199]  # indices 1194,1195,1196,1197,1198

# Remove the orphaned lines
del lines[1194:1199]

# Now find the line 'RESPONSIBILITY_TYPES = ('
insert_idx = None
for i, line in enumerate(lines):
    if 'RESPONSIBILITY_TYPES = (' in line:
        insert_idx = i + 1
        break

if insert_idx is not None:
    # Insert the items after RESPONSIBILITY_TYPES = (
    for i, item in enumerate(lines[1194:1199]):
        lines.insert(insert_idx + i, item)
else:
    print("ERROR: Could not find RESPONSIBILITY_TYPES = (")

with open('app/models/execution_strategy.py', 'w') as f:
    f.writelines(lines)

print('Fixed')
import re

# Read the org_relationships.txt file
with open('D:\\vcos1\\workspace\\vcos\\backend\\org_relationships.txt', 'r') as f:
    relationships = f.read().strip().split('\n')

# Read the organization.py file
with open('D:\\vcos1\\workspace\\vcos\\backend\\app\\models\\organization.py', 'r') as f:
    content = f.read()

# Find the insertion point - after the existing relationships
# Look for the line with "capability_lifecycle_records"
insert_marker = "capability_lifecycle_records: Mapped[List[\"CapabilityLifecycleRecord\"]] = relationship("

# Find the end of that relationship block
marker_pos = content.find(insert_marker)
if marker_pos == -1:
    print("Marker not found!")
    exit(1)

# Find the end of that block (the closing ) and newline)
end_pos = content.find(")\n", marker_pos)
if end_pos == -1:
    print("End of block not found!")
    exit(1)

# Insert after the closing )
insert_pos = end_pos + 2

# Build the new relationships
new_relationships = "\n"
for line in relationships:
    if line.strip():
        new_relationships += "    " + line.strip() + "\n"

# Insert the new relationships
new_content = content[:insert_pos] + new_relationships + content[insert_pos:]

# Write back
with open('D:\\vcos1\\workspace\\vcos\\backend\\app\\models\\organization.py', 'w') as f:
    f.write(new_content)

print("Successfully added relationships to organization.py")
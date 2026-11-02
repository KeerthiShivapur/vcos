import re
import os

models_dir = r"D:\vcos1\workspace\vcos\backend\app\models"

# Find all models with ForeignKey to organizations.id and their back_populates
relationships = {}

for filename in os.listdir(models_dir):
    if filename.endswith('.py') and not filename.startswith('__'):
        filepath = os.path.join(models_dir, filename)
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
            
        # Find class name
        class_match = re.search(r'class\s+(\w+)\s*\(', content)
        if not class_match:
            continue
        class_name = class_match.group(1)
        
        # Find ForeignKey to organizations.id
        fk_matches = re.findall(r'ForeignKey\(["\']organizations\.id["\'][^)]*\)', content)
        if not fk_matches:
            continue
            
        # Find back_populates
        bp_matches = re.findall(r'back_populates\s*=\s*["\']([^"\']+)["\']', content)
        
        for bp in bp_matches:
            if bp not in relationships:
                relationships[bp] = []
            relationships[bp].append(class_name)

# Generate the relationship code
code = ""
for bp, classes in sorted(relationships.items()):
    # Deduplicate classes
    unique_classes = list(dict.fromkeys(classes))
    for cls in unique_classes:
        code += f'    {bp}: Mapped[List["{cls}"]] = relationship(back_populates="organization", cascade="all, delete-orphan")\n'

# Write to file
with open('D:\\vcos1\\workspace\\vcos\\backend\\org_relationships.txt', 'w') as f:
    f.write(code)

print("Relationship code generated in org_relationships.txt")
print(f"Total relationships: {sum(len(v) for v in relationships.values())}")
print(f"Unique back_populates names: {len(relationships)}")
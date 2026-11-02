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
        
        # Find ForeignKey to organizations.id and back_populates
        fk_matches = re.findall(r'ForeignKey\("organizations\.id"[^)]*\)', content)
        if not fk_matches:
            continue
            
        # Find back_populates
        bp_matches = re.findall(r'back_populates\s*=\s*["\']([^"\']+)["\']', content)
        
        for bp in bp_matches:
            if bp not in relationships:
                relationships[bp] = []
            relationships[bp].append(class_name)

print("Missing relationships in Organization:")
for bp, classes in sorted(relationships.items()):
    for cls in classes:
        print(f"    {bp}: Mapped[List[\"{cls}\"]] = relationship(back_populates=\"organization\", cascade=\"all, delete-orphan\")")

# Also find models without back_populates that reference organizations
print("\n\nModels with FK to organizations but no back_populates:")
for filename in os.listdir(models_dir):
    if filename.endswith('.py') and not filename.startswith('__'):
        filepath = os.path.join(models_dir, filename)
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        
        if 'ForeignKey("organizations.id"' in content or "ForeignKey('organizations.id'" in content:
            # Check if it has back_populates
            if 'back_populates' not in content:
                class_match = re.search(r'class\s+(\w+)\s*\(', content)
                if class_match:
                    print(f"    {class_match.group(1)} - NO back_populates")
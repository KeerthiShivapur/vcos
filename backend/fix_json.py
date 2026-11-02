import re

with open('tests/acceptance/adapters.py', 'r') as f:
    content = f.read()

# Fix dict to JSON string for resource_requirements and resource_constraints
content = content.replace(
    'resource_requirements={},\n                resource_constraints={},',
    'resource_requirements="{}",\n                resource_constraints="{}",'
)

# Also fix any other dict values that should be JSON strings
content = re.sub(
    r'(\w+)=\{\},\s*',
    r'\1="{}",',
    content
)

with open('tests/acceptance/adapters.py', 'w') as f:
    f.write(content)

print('Fixed dict to JSON string issues')
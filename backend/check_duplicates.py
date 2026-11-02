import re

with open('app/testing/failure_injection.py', 'r') as f:
    content = f.read()

# Find all enum values
matches = re.findall(r'(\w+)\s*=\s*["\']([^"\']+)["\']', content)
values = {}
for name, value in matches:
    if value in values:
        print(f'Duplicate: {value} = {values[value]} and {name}')
    else:
        values[value] = name

print("Done")
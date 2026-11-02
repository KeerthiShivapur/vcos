import re

with open('tests/acceptance/adapters.py', 'r') as f:
    content = f.read()

# Check what classes are defined
classes = re.findall(r'^class (\w+)\(.*?\):', content, re.MULTILINE)
print('Defined classes:')
for c in classes:
    print('  ' + c)

# Check what's in the registry
registry_start = content.find('ADAPTER_REGISTRY')
if registry_start >= 0:
    registry_text = content[registry_start:]
    keys = re.findall(r'"([^"]+)":\s*(\w+)', registry_text)
    print('\nRegistry entries:')
    for k, v in keys:
        print('  ' + k + ': ' + v)
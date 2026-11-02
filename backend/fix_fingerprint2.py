import re

with open('tests/test_gate32_canonical_reliability.py', 'r') as f:
    content = f.read()

# Remove fingerprint=... from create_operation calls
# Pattern: fingerprint="[^"]*",\s* (including the comma and whitespace)
pattern = r'fingerprint="[^"]*",\s*'
content = re.sub(pattern, '', content)

with open('tests/test_gate32_canonical_reliability.py', 'w') as f:
    f.write(content)

print('Removed fingerprint params')
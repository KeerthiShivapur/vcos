import re

with open('app/intelligence/canonical_integration_service.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Replace triple-quoted docstrings with single-quoted strings
# Pattern 1: """text""" on a single line -> 'text'
content = re.sub(r'"""([^"]*)"""', r"'\1'", content)

# Pattern 2: multi-line triple-quoted strings (more complex)
# For now, just handle single-line docstrings

with open('app/intelligence/canonical_integration_service.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Converted triple-quoted docstrings to single-quoted strings')
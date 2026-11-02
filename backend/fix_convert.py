import re

with open('app/intelligence/canonical_integration_service.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Convert all triple-quoted strings to single-quoted strings
# Handle both single-line and multi-line docstrings

# First, handle single-line triple-quoted strings: """text"""
content = re.sub(r'"""([^"]*)"""', r"'\1'", content)

# For multi-line triple-quoted strings, we need a more sophisticated approach
# For now, let's just ensure the file parses by fixing the specific syntax errors

with open('app/intelligence/canonical_integration_service.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Done')
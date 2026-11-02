#!/usr/bin/env python3
"""Remove fingerprint params from create_operation calls in tests."""

import re

with open('tests/test_gate32_canonical_reliability.py', 'r') as f:
    content = f.read()

# Remove fingerprint=... from create_operation calls
content = re.sub(r'fingerprint="[^"]*",\s*\n', '', content)

with open('tests/test_gate32_canonical_reliability.py', 'w') as f:
    f.write(content)

print('Removed fingerprint params')
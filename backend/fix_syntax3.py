#!/usr/bin/env python3
"""Fix the ExternalUnknownState syntax error."""

with open('tests/test_gate32_canonical_reliability.py', 'r') as f:
    content = f.read()

# Fix the problematic line
content = content.replace(
    '            request_        )\n',
    '            request_fingerprint="fp-req-1",\n        )\n'
)

with open('tests/test_gate32_canonical_reliability.py', 'w') as f:
    f.write(content)

print('Fixed ExternalUnknownState')
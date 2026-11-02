# Fix the fingerprint parameter in create_operation call at line 875
with open('tests/test_gate32_canonical_reliability.py', 'r') as f:
    content = f.read()

# Replace the specific line
content = content.replace(
    '                fingerprint=f"scan-fp-{i}",\n',
    ''
)

with open('tests/test_gate32_canonical_reliability.py', 'w') as f:
    f.write(content)

print('Fixed scan-fp line')
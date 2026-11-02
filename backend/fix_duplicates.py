import re

with open('D:\\vcos1\\workspace\\vcos\\backend\\tests\\test_gate8_5_canonical_organizational_intelligence.py', 'r') as f:
    content = f.read()

# Fix duplicate state parameters - replace the pattern where state appears twice
content = re.sub(
    r'(state="completed",\s*\n\s*)state="completed",\s*\n(\s*completed_at=utcnow\(\),)',
    r'\1\2',
    content
)

with open('D:\\vcos1\\workspace\\vcos\\backend\\tests\\test_gate8_5_canonical_organizational_intelligence.py', 'w') as f:
    f.write(content)

print('Fixed duplicate state parameters')
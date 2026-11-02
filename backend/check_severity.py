import re
with open('tests/test_phase_i6_decision_intelligence.py', 'r') as f:
    content = f.read()
pattern = r'severity\s*=\s*["\']([^"\']+)["\']'
for m in re.finditer(pattern, content):
    print(m.group(1))
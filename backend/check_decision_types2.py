import re
with open('tests/test_phase_i6_decision_intelligence.py', 'r') as f:
    content = f.read()
# Find the failing test functions and their decision_type usage
for m in re.finditer(r'test_decision_intelligence_(ask_question|deterministic_synthesis)', content):
    start = max(0, m.start() - 200)
    end = min(len(content), m.end() + 2000)
    snippet = content[start:end]
    for m2 in re.finditer(r'decision_type\s*=\s*["\']([^"\']+)["\']', snippet):
        print(m2.group(1))
    print('---')
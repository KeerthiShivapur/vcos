import re
with open('tests/test_phase_i6_decision_intelligence.py', 'r') as f:
    content = f.read()
# Find the deterministic_synthesis test
idx = content.find('def test_decision_intelligence_deterministic_synthesis')
if idx >= 0:
    end = content.find('def test_', idx + 1)
    if end == -1:
        end = len(content)
    snippet = content[idx:end]
    for m in re.finditer(r'decision_type\s*=\s*["\']([^"\']+)["\']', snippet):
        print(f'  decision_type: {m.group(1)}')
    print('---')
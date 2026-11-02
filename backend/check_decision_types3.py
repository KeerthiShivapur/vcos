import re
with open('tests/test_phase_i6_decision_intelligence.py', 'r') as f:
    content = f.read()
# Find the failing test functions and their decision_type usage
for test_name in ['test_decision_intelligence_ask_question', 'test_decision_intelligence_deterministic_synthesis']:
    idx = content.find(f'def {test_name}')
    if idx >= 0:
        end = content.find('def test_', idx + 1)
        if end == -1:
            end = len(content)
        snippet = content[idx:end]
        for m in re.finditer(r'decision_type\s*=\s*["\']([^"\']+)["\']', snippet):
            print(f'{m.group(1)}')
        print('---')
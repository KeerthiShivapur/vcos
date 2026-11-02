import re
with open('tests/test_phase_i7_governed_commitment.py', 'r') as f:
    content = f.read()
matches = list(re.finditer(r'transition_commitment\([^)]+new_state="active"', content))
for m in matches:
    start = max(0, m.start()-200)
    end = min(len(content), m.end()+200)
    print(content[start:end])
    print('---')
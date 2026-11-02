import re
with open('tests/test_phase_i7_governed_commitment.py', 'r') as f:
    content = f.read()
matches = list(re.finditer(r'new_state="active"', content))
for m in matches:
    start = max(0, m.start()-100)
    end = min(len(content), m.end()+100)
    print(content[start:end])
    print('---')
import re
with open('tests/test_phase_i6_decision_intelligence.py', 'r') as f:
    content = f.read()
for m in re.finditer(r'test_decision_intelligence_(ask_question|deterministic_synthesis)', content):
    print(m.group(1))
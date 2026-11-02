with open('tests/test_phase_i3_alignment.py', 'r') as f:
    content = f.read()
import re
# Find all UPPER_CASE identifiers
vocabs = re.findall(r'\b[A-Z_]{3,}\b', content)
print(sorted(set(vocabs)))
with open('tests/acceptance/adapters.py', 'r') as f:
    content = f.read()

# Find all 'policy' references
import re
results = []
for m in re.finditer(r'policy', content):
    pos = m.start()
    results.append(repr(content[max(0,pos-50):pos+50]))

with open('policy_refs.txt', 'w') as f:
    for r in results:
        f.write(r + '\n---\n')

print(f'Found {len(results)} references')
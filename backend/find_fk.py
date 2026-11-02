with open('app/models/canonical_reliability.py', 'r') as f:
    content = f.read()

# Find all occurrences of canonical_operations in ForeignKey
import re
matches = [(m.start(), m.group()) for m in re.finditer(r'ForeignKey\("canonical_operations', content)]
for start, match in matches:
    print('Position:', start)
    print(content[max(0,start-50):start+100])
    print('---')
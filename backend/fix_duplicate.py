with open('app/services/canonical_fingerprint.py', 'r') as f:
    content = f.read()

# Remove duplicate aggregate_fingerprint method
lines = content.split('\n')
new_lines = []
skip = False
for i, line in enumerate(lines):
    if 'def aggregate_fingerprint' in line and skip:
        skip = True
        continue
    if 'def aggregate_fingerprint' in line:
        if skip:
            continue
        skip = True
    new_lines.append(line)

content = '\n'.join(new_lines)

with open('app/services/canonical_fingerprint.py', 'w') as f:
    f.write(content)
print('Done')
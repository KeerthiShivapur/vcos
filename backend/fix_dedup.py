with open('app/services/canonical_fingerprint.py', 'r') as f:
    lines = f.readlines()

new_lines = []
skip = False
for line in lines:
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
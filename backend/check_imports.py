with open('app/intelligence/canonical_concurrency.py', 'rb') as f:
    content = f.read()

lines = content.split(b'\n')
for i, line in enumerate(lines[:50]):
    decoded = line.decode('utf-8', errors='replace')
    print(str(i) + ': ' + decoded)
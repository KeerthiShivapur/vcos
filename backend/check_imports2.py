import sys
sys.stdout.reconfigure(encoding='utf-8')

with open('app/intelligence/canonical_concurrency.py', 'r', encoding='utf-8', errors='replace') as f:
    lines = f.readlines()

for i, line in enumerate(lines[:50]):
    print(f"{i}: {line.rstrip()}")
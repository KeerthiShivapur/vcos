import ast

with open('app/core/realtime/crdt.py', 'r', encoding='utf-8') as f:
    source = f.read()

# Try to find the exact issue
lines = source.split('\n')
for i in range(475, 510):
    line = lines[i]
    print(f"{i+1:4d}: {repr(line)}")
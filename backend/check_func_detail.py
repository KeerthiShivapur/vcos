with open('app/core/realtime/crdt.py', 'rb') as f:
    data = f.read()
lines = data.split(b'\n')

# Print lines 479-510 with exact indentation
for i in range(478, 510):
    line = lines[i]
    leading = len(line) - len(line.lstrip(b' \t'))
    print(f"{i+1:4d}: leading={leading:2d} {line[:120]}")
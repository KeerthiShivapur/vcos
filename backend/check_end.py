with open('app/core/realtime/crdt.py', 'rb') as f:
    data = f.read()

# Check last 50 lines
lines = data.split(b'\n')
for i in range(max(0, len(lines)-50), len(lines)):
    print(f"{len(lines)-50+i+1:4d}: {lines[i][:100]}")
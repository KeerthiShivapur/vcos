with open('app/core/realtime/crdt.py', 'rb') as f:
    data = f.read()
lines = data.split(b'\n')
print('Total lines:', len(lines))
print('Last line:', lines[-1] if lines else b'empty')
print('Last 10 lines:')
for i in range(max(0, len(lines)-20), len(lines)):
    print(f"{i+1:4d}: {lines[i][:100]}")
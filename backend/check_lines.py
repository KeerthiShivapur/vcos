with open('app/core/realtime/crdt.py', 'rb') as f:
    lines = f.readlines()
    for i in range(480, 510):
        print(f"{i+1}: {repr(lines[i])}")
lines = open('app/core/realtime/crdt.py', 'r', encoding='utf-8').readlines()
for i in range(475, 510):
    line = lines[i]
    print(f"{i+1:4d}: {repr(line)}")
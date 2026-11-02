with open('app/core/realtime/crdt.py', 'rb') as f:
    data = f.read()
    lines = data.split(b'\n')
    line = lines[481]
    print('Length:', len(line))
    print('Hex:', ' '.join(f'{b:02x}' for b in line))
with open('app/core/realtime/crdt.py', 'rb') as f:
    content = f.read()
    print('BOM:', content[:3])
    print('Length:', len(content))
    lines = content.split(b'\n')
    print('Line 482:', lines[481])
    print('Line 483:', lines[482])
    print('Line 484:', lines[483])
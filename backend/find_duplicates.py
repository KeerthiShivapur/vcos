with open('D:\\vcos1\\workspace\\vcos\\backend\\tests\\test_gate8_5_canonical_organizational_intelligence.py', 'r') as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if 'state="completed"' in line:
        if i > 0 and 'state="completed"' in lines[i-1]:
            print(f'Line {i+1}: {line.strip()}')
            print(f'Previous line {i}: {lines[i-1].strip()}')
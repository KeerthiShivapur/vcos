with open('app/intelligence/cohort_builder.py', 'rb') as f:
    content = f.read()
    lines = content.split(b'\n')
    for i in range(293, 310):
        line = lines[i]
        for j, b in enumerate(line):
            if b == 9:  # tab
                print(f'TAB at line {i+1}, pos {j}')
            if b > 127:
                print(f'Non-ASCII at line {i+1}, pos {j}: byte={b} ({chr(b) if b < 128 else "?"})')
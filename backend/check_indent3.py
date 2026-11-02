with open('D:/vcos1/workspace/vcos/backend/app/intelligence/cohort_builder.py', 'rb') as f:
    content = f.read()
    lines = content.split(b'\n')
    for i in range(293, 310):
        line = lines[i]
        print(f'Line {i+1}: len={len(line)}, starts_space={line.startswith(b" ")}, starts_tab={line.startswith(b"\t")}, repr={repr(line)}')
        # Check each byte in the leading whitespace
        leading = len(line) - len(line.lstrip())
        for j in range(min(leading, len(line))):
            b = line[j]
            if b != 32 and b != 9:
                print(f'  Line {i+1}, pos {j}: unexpected byte {b} ({chr(b) if b < 128 else "?"})')
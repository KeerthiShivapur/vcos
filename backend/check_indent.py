with open('app/core/realtime/crdt.py', 'rb') as f:
    data = f.read()
    lines = data.split(b'\n')
    
    # Check for mixed tabs and spaces in the function
    for i in range(478, 510):
        line = lines[i]
        tabs = line.count(b'\t')
        spaces = line.count(b' ')
        leading_spaces = len(line) - len(line.lstrip(b' \t'))
        print(f"Line {i+1}: tabs={tabs}, spaces={spaces}, leading={leading_spaces}, content={lines[i][:80]}")
with open('app/models/execution_strategy.py', 'r') as f:
    lines = f.readlines()
    for i, line in enumerate(lines):
        if 'VERIFICATION_STATES' in line:
            print(f'Line {i+1}: {repr(line)}')
            print('  strip():', repr(line.strip()))
            print('  == "VERIFICATION_STATES = (":', line.strip() == 'VERIFICATION_STATES = (')
            print('  in line:', 'VERIFICATION_STATES = (' in line)
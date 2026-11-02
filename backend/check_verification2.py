with open('app/models/execution_strategy.py', 'r') as f:
    lines = f.readlines()
    for i, line in enumerate(lines):
        if 'VERIFICATION_STATES' in line:
            print(f'Line {i+1}: {repr(line)}')
            print('  Contains VERIFICATION_STATES = (: ', 'VERIFICATION_STATES = (' in line)
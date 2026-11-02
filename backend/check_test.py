with open('tests/test_phase_i7_governed_commitment.py', 'rb') as f:
    content = f.read()
idx = content.find(b'new_state="active"')
if idx >= 0:
    print(content[max(0,idx-200):idx+200])
    print()
    print(repr(content[idx:idx+30]))
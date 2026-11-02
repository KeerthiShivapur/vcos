with open('tests/acceptance/test_backup_restore_roundtrip.py', 'r') as f:
    content = f.read()

# Find the duplicate operation_type
idx = content.find('operation_type="test"')
if idx >= 0:
    # Find the second occurrence
    idx2 = content.find('operation_type="test"', idx + 20)
    if idx2 >= 0:
        print('Found second at:', idx2)
        print('Context:', repr(content[idx2:idx2+100]))
    else:
        print('Only one found')
else:
    print('Not found')
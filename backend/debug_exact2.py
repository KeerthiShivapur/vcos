with open('tests/acceptance/test_deployment_dr_production_verification.py', 'r', encoding='utf-8') as f:
    content = f.read()

idx = content.find('Incomplete restore correctly rejected on real PostgreSQL')
if idx >= 0:
    with open('debug_output.txt', 'w', encoding='utf-8') as f:
        f.write(content[idx:idx+500])
    print('Written to debug_output.txt')
else:
    print('Not found')
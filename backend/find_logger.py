with open('tests/acceptance/test_deployment_dr_production_verification.py', 'r', encoding='utf-8') as f:
    content = f.read()

idx = content.find('logger.info("')
if idx >= 0:
    with open('debug_block3.txt', 'w', encoding='utf-8') as f:
        f.write(content[idx:idx+500])
    print('Written to debug_block3.txt')
else:
    print('Not found')
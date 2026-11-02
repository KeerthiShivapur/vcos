with open('tests/acceptance/test_production_deployment_dr_e2e.py', 'r', encoding='utf-8') as f:
    content = f.read()

idx = content.find('assert memory_count > 0')
if idx == -1:
    print('Not found')
else:
    start = max(0, idx - 300)
    end = min(len(content), idx + 200)
    with open('debug_assert3.txt', 'w', encoding='utf-8') as f:
        f.write(content[start:end])
    print('Written to debug_assert3.txt')
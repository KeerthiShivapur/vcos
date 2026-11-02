with open('tests/acceptance/test_deployment_dr_production_verification.py', 'r', encoding='utf-8') as f:
    content = f.read()

idx = content.find('test_incomplete_restore_rejection_real_pg')
if idx >= 0:
    with open('test_section.txt', 'w', encoding='utf-8') as f:
        f.write(content[idx:idx+800])
    print("Written to test_section.txt")
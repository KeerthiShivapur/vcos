with open('tests/acceptance/test_deployment_dr_production_verification.py', 'r', encoding='utf-8') as f:
    content = f.read()

idx = content.find('org = production_company_real_pg["organization"]')
if idx >= 0:
    with open('found_text.txt', 'w', encoding='utf-8') as f:
        f.write(content[idx:idx+500])
    print("Found at index:", idx)
else:
    print("Not found")
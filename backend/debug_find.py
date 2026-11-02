with open('tests/acceptance/test_deployment_dr_production_verification.py', 'r', encoding='utf-8') as f:
    content = f.read()

idx = content.find('assert "not found" in result["error"].lower()')
if idx >= 0:
    print(repr(content[idx:idx+300]))
else:
    print("Not found")
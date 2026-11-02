with open('tests/acceptance/test_deployment_dr_production_verification.py', 'r', encoding='utf-8') as f:
    content = f.read()

idx = content.find('assert "not found" in result["error"].lower()')
if idx >= 0:
    # Write to file to avoid encoding issues
    with open('debug_output.txt', 'w', encoding='utf-8') as f:
        f.write(content[idx:idx+300])
    print("Written to debug_output.txt")
else:
    print("Not found")
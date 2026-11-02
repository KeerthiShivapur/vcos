with open('tests/acceptance/test_deployment_dr_production_verification.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Fix line 1654 - missing indentation
lines[1653] = '        logger.info("=== Recovery Authorization Test (Real PostgreSQL) ===")\n'

with open('tests/acceptance/test_deployment_dr_production_verification.py', 'w', encoding='utf-8') as f:
    f.writelines(lines)

print("Fixed indentation")
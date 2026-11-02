with open('tests/acceptance/test_deployment_dr_production_verification.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Fix line 1105 - add indentation
lines[1104] = '        logger.info("=== PHASE 12: RPO/RTO MEASUREMENT ===")\n'

with open('tests/acceptance/test_deployment_dr_production_verification.py', 'w', encoding='utf-8') as f:
    f.writelines(lines)

print("Fixed line 1105")
with open('tests/acceptance/test_deployment_dr_production_verification.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Fix line 1135 - remove extra indentation
lines[1134] = '        final_measurement = measurement_service.complete_measurement(\n'

with open('tests/acceptance/test_deployment_dr_production_verification.py', 'w', encoding='utf-8') as f:
    f.writelines(lines)

print("Fixed line 1135")
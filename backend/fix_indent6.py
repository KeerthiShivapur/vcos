with open('tests/acceptance/test_deployment_dr_production_verification.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Fix line 1134 (blank line with 8 spaces) and 1135 (8 spaces -> 4 spaces)
lines[1133] = '        \n'  # blank line with 8 spaces -> 8 spaces (correct for this block)
lines[1134] = '        final_measurement = measurement_service.complete_measurement(\n'  # 8 spaces

with open('tests/acceptance/test_deployment_dr_production_verification.py', 'w', encoding='utf-8') as f:
    f.writelines(lines)

print("Fixed lines 1134-1135")
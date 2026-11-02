with open('tests/acceptance/test_deployment_dr_production_verification.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Print lines around 1630-1650
for i, line in enumerate(lines[1625:1660], 1626):
    print(f'{i}: {line.rstrip()}')

with open('print_output.txt', 'w', encoding='utf-8') as f:
    for i, line in enumerate(lines[1625:1660], 1626):
        f.write(f'{i}: {line}')
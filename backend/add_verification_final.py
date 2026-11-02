with open('app/models/execution_strategy.py', 'r') as f:
    lines = f.readlines()

# Find VERIFICATION_STATES and add VERIFICATION_TRIGGERS after it
insert_idx = None
for i, line in enumerate(lines):
    if 'VERIFICATION_STATES = (' in line:
        print(f'Found at line {i+1}: {repr(line)}')
        # Find the closing ) of VERIFICATION_STATES
        for j in range(i, len(lines)):
            if lines[j].strip() == ')':
                insert_idx = j + 1
                print(f'Found closing ) at line {j+1}: {repr(lines[j])}')
                break
            break

if insert_idx is not None:
    print(f'Insert index: {insert_idx} (line {insert_idx + 1})')
    items_to_insert = [
        '\n',
        'VERIFICATION_TRIGGERS = (\n',
        '    "plan_vs_reality",\n',
        '    "commitment_fulfillment",\n',
        '    "objective_achievement",\n',
        '    "capacity_exceeded",\n',
        '    "dependency_risk",\n',
        '    "budget_variance",\n',
        '    "timeline_deviation",\n',
        '    "quality_degradation",\n',
        '    "risk_threshold_breach",\n',
        ')\n',
        '\n',
    ]

    for i, item in enumerate([
        '\n',
        'VERIFICATION_TRIGGERS = (\n',
        '    "plan_vs_reality",\n',
        '    "commitment_fulfillment",\n',
        '    "objective_achievement",\n',
        '    "capacity_exceeded",\n',
        '    "dependency_risk",\n',
        '    "budget_variance",\n',
        '    "timeline_deviation",\n',
        '    "quality_degradation",\n',
        '    "risk_threshold_breach",\n',
        ')\n',
        '\n',
    ]):
        lines.insert(insert_idx + 1 + i, item)

    with open('app/models/execution_strategy.py', 'w') as f:
        f.writelines(lines)
    print('Added VERIFICATION_TRIGGERS')
else:
    print('VERIFICATION_STATES not found')
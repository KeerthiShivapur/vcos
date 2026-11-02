with open('app/models/execution_strategy.py', 'r') as f:
    lines = f.readlines()

# Find VERIFICATION_TRIGGERS and add VERIFICATION_TYPES after it
insert_idx = None
for i, line in enumerate(lines):
    if 'VERIFICATION_TRIGGERS = (' in line:
        for j in range(i, min(i+20, len(lines))):
            if lines[j].strip() == ')':
                insert_idx = j + 1
                break
            break

if insert_idx is not None:
    items_to_insert = [
        '\n',
        'VERIFICATION_TYPES = (\n',
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
        'VERIFICATION_TYPES = (\n',
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
    print('Added VERIFICATION_TYPES')
else:
    print('VERIFICATION_TRIGGERS not found')
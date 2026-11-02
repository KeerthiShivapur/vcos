with open('app/models/execution_strategy.py', 'r') as f:
    content = f.read()

# Find VERIFICATION_TRIGGERS and add VERIFICATION_TYPES after it
idx = content.find('VERIFICATION_TRIGGERS = (')
if idx >= 0:
    # Find the closing ) of VERIFICATION_TRIGGERS
    idx = content.find(')\n', idx)
    if idx >= 0:
        insert_pos = idx + 2  # skip )\n
        new_content = content[:idx+2] + '\nVERIFICATION_TYPES = (\n    "plan_vs_reality",\n    "commitment_fulfillment",\n    "objective_achievement",\n    "capacity_exceeded",\n    "dependency_risk",\n    "budget_variance",\n    "timeline_deviation",\n    "quality_degradation",\n    "risk_threshold_breach",\n)\n\n' + content[idx+2:]
        with open('app/models/execution_strategy.py', 'w') as f:
            f.write(new_content)
        print('Added VERIFICATION_TYPES')
    else:
        print('Could not find end of VERIFICATION_TRIGGERS')
else:
    print('VERIFICATION_TRIGGERS not found')
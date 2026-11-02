import codecs

with codecs.open('tests/acceptance/test_production_deployment_dr_e2e.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix the Plan model - the simple replacement changed 'description' to 'rationale' in Plan too
# Plan model uses 'description', not 'rationale'

# Fix starter plan
old_starter = '''        starter_plan = Plan(
            key="starter",
            name="Starter",
            rationale="Starter plan for small teams",
            tier="starter",
            monthly_price_cents=0,
            annual_price_cents=0,
            currency="USD",
            intervals=["monthly", "annual"],
            entitlements={
                "employees.max": {"type": "limit", "value": 10},
                "storage.gb": {"type": "limit", "value": 10},
            },
            features={},
            limits={},
            is_active=True,
            is_public=True,
        )'''

new_starter = '''        starter_plan = Plan(
            key="starter",
            name="Starter",
            description="Starter plan for small teams",
            tier="starter",
            monthly_price_cents=0,
            annual_price_cents=0,
            currency="USD",
            intervals=["monthly", "annual"],
            entitlements={
                "employees.max": {"type": "limit", "value": 10},
                "storage.gb": {"type": "limit", "value": 10},
            },
            features={},
            limits={},
            is_active=True,
            is_public=True,
        )'''

# Fix professional plan
old_prof = '''        prof_plan = Plan(
            key="professional",
            name="Professional",
            rationale="Professional plan for growing teams",
            tier="professional",
            monthly_price_cents=2900,
            annual_price_cents=29000,
            currency="USD",
            intervals=["monthly", "annual"],
            entitlements={
                "employees.max": {"type": "limit", "value": 100},
                "storage.gb": {"type": "limit", "value": 100},
            },
            features={},
            limits={},
            is_active=True,
            is_public=True,
        )'''

new_prof = '''        prof_plan = Plan(
            key="professional",
            name="Professional",
            description="Professional plan for growing teams",
            tier="professional",
            monthly_price_cents=2900,
            annual_price_cents=29000,
            currency="USD",
            intervals=["monthly", "annual"],
            entitlements={
                "employees.max": {"type": "limit", "value": 100},
                "storage.gb": {"type": "limit", "value": 100},
            },
            features={},
            limits={},
            is_active=True,
            is_public=True,
        )'''

if old_starter in content:
    content = content.replace(old_starter, new_starter)
    print('Fixed starter plan')

if old_prof in content:
    content = content.replace(old_prof, new_prof)
    print('Fixed professional plan')

with codecs.open('tests/acceptance/test_production_deployment_dr_e2e.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Fixed Plan model')
with open('create_company_state.py', 'r') as f:
    content = f.read()

# Remove fingerprint from CompanyGoal creation
content = content.replace(
    '''goal1 = CompanyGoal(
                organization_id=org.id,
                title="Platform Modernization Complete",
                description="Complete migration to PostgreSQL 18 and new API gateway",
                status="active",
                priority=1,
                kind="efficiency",
                fingerprint=f"fp-{uuid.uuid4().hex[:16]}"
            )
            goal2 = CompanyGoal(
                organization_id=org.id,
                title="Customer Satisfaction Improvement",
                description="Increase customer satisfaction score to 4.5+",
                status="active",
                priority=2,
                kind="growth",
                fingerprint=f"fp-{uuid.uuid4().hex[:16]}"
            )''',
    '''goal1 = CompanyGoal(
                organization_id=org.id,
                title="Platform Modernization Complete",
                description="Complete migration to PostgreSQL 18 and new API gateway",
                status="active",
                priority=1,
                kind="efficiency"
            )
            goal2 = CompanyGoal(
                organization_id=org.id,
                title="Customer Satisfaction Improvement",
                description="Increase customer satisfaction score to 4.5+",
                status="active",
                priority=2,
                kind="growth"
            )''')

with open('create_company_state.py', 'w') as f:
    f.write(content)
print('Fixed CompanyGoal - removed fingerprint')
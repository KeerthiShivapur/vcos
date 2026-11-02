with open('create_company_state.py', 'r') as f:
    content = f.read()

# Add fingerprint to CompanyObjective
content = content.replace(
    '''            obj1 = CompanyObjective(
                organization_id=org.id,
                goal_id=goal1.id,
                title="Complete PostgreSQL 18 Migration",
                description="Migrate all databases to PostgreSQL 18 by end of Q3",
                status="active",
            )''',
    '''            obj1 = CompanyObjective(
                organization_id=org.id,
                goal_id=goal1.id,
                title="Complete PostgreSQL 18 Migration",
                description="Migrate all databases to PostgreSQL 18 by end of Q3",
                status="active",
                fingerprint=f"fp-{uuid.uuid4().hex[:16]}"
            )'''
)

content = content.replace(
    '''            obj2 = CompanyObjective(
                organization_id=org.id,
                goal_id=goal1.id,
                title="Deploy New API Gateway",
                description="Deploy new API gateway with improved rate limiting",
                status="active",
            )''',
    '''            obj2 = CompanyObjective(
                organization_id=org.id,
                goal_id=goal1.id,
                title="Deploy New API Gateway",
                description="Deploy new API gateway with improved rate limiting",
                status="active",
                fingerprint=f"fp-{uuid.uuid4().hex[:16]}"
            )'''
)

content = content.replace(
    '''            obj3 = CompanyObjective(
                organization_id=org.id,
                goal_id=goal2.id,
                title="Improve CSAT Score",
                description="Implement customer feedback loop and improve CSAT",
                status="active",
            )''',
    '''            obj3 = CompanyObjective(
                organization_id=org.id,
                goal_id=goal2.id,
                title="Improve CSAT Score",
                description="Implement customer feedback loop and improve CSAT",
                status="active",
                fingerprint=f"fp-{uuid.uuid4().hex[:16]}"
            )'''
)

# Add fingerprint to CompanyInitiative
content = content.replace(
    '''            init1 = CompanyInitiative(
                organization_id=org.id,
                objective_id=obj1.id,
                title="Database Migration Project",
                description="Migrate all databases to PostgreSQL 18",
                status="active",
            )''',
    '''            init1 = CompanyInitiative(
                organization_id=org.id,
                objective_id=obj1.id,
                title="Database Migration Project",
                description="Migrate all databases to PostgreSQL 18",
                status="active",
                fingerprint=f"fp-{uuid.uuid4().hex[:16]}"
            )'''
)

with open('create_company_state.py', 'w') as f:
    f.write(content)
print('Added fingerprints to CompanyObjective and CompanyInitiative')
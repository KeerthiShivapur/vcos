import codecs

with codecs.open('tests/acceptance/test_production_deployment_dr_e2e.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix Department - revert rationale back to description
old_dept = '''        dept_engineering = Department(
            id=f"dept-eng-{uuid.uuid4().hex[:8]}",
            organization_id=org.id,
            name="Engineering",
            code="ENG",
            rationale="Engineering Department",
        )'''

new_dept = '''        dept_engineering = Department(
            id=f"dept-eng-{uuid.uuid4().hex[:8]}",
            organization_id=org.id,
            name="Engineering",
            code="ENG",
            description="Engineering Department",
        )'''

if old_dept in content:
    content = content.replace(old_dept, new_dept)
    print('Fixed Engineering department')

old_dept2 = '''        dept_sales = Department(
            id=f"dept-sales-{uuid.uuid4().hex[:8]}",
            organization_id=org.id,
            name="Sales",
            code="SAL",
            rationale="Sales Department",
        )'''

new_dept2 = '''        dept_sales = Department(
            id=f"dept-sales-{uuid.uuid4().hex[:8]}",
            organization_id=org.id,
            name="Sales",
            code="SAL",
            description="Sales Department",
        )'''

if old_dept2 in content:
    content = content.replace(old_dept2, new_dept2)
    print('Fixed Sales department')

# Fix Team model
old_team = '''        team_backend = Team(
            id=f"team-backend-{uuid.uuid4().hex[:8]}",
            organization_id=org.id,
            name="Backend Engineering",
            code="BE",
            department_id=dept_engineering.id,
            rationale="Backend Development Team",
        )'''

new_team = '''        team_backend = Team(
            id=f"team-backend-{uuid.uuid4().hex[:8]}",
            organization_id=org.id,
            name="Backend Engineering",
            code="BE",
            department_id=dept_engineering.id,
            description="Backend Development Team",
        )'''

if old_team in content:
    content = content.replace(old_team, new_team)
    print('Fixed Backend team')

old_team2 = '''        team_frontend = Team(
            id=f"team-frontend-{uuid.uuid4().hex[:8]}",
            organization_id=org.id,
            name="Frontend Engineering",
            code="FE",
            department_id=dept_engineering.id,
            rationale="Frontend Development Team",
        )'''

new_team2 = '''        team_frontend = Team(
            id=f"team-frontend-{uuid.uuid4().hex[:8]}",
            organization_id=org.id,
            name="Frontend Engineering",
            code="FE",
            department_id=dept_engineering.id,
            description="Frontend Development Team",
        )'''

if old_team2 in content:
    content = content.replace(old_team2, new_team2)
    print('Fixed Frontend team')

# Fix Project model
old_project = '''        project_platform = Project(
            id=f"proj-platform-{uuid.uuid4().hex[:8]}",
            organization_id=org.id,
            name="Platform Modernization",
            code="PLAT",
            rationale="Modernize core platform",
            status="active",
        )'''

new_project = '''        project_platform = Project(
            id=f"proj-platform-{uuid.uuid4().hex[:8]}",
            organization_id=org.id,
            name="Platform Modernization",
            code="PLAT",
            description="Modernize core platform",
            status="active",
        )'''

if old_project in content:
    content = content.replace(old_project, new_project)
    print('Fixed Platform project')

old_project2 = '''        project_customer = Project(
            id=f"proj-customer-{uuid.uuid4().hex[:8]}",
            organization_id=org.id,
            name="Customer Portal",
            code="CUST",
            rationale="Build customer portal",
            status="active",
        )'''

new_project2 = '''        project_customer = Project(
            id=f"proj-customer-{uuid.uuid4().hex[:8]}",
            organization_id=org.id,
            name="Customer Portal",
            code="CUST",
            description="Build customer portal",
            status="active",
        )'''

if old_project2 in content:
    content = content.replace(old_project2, new_project2)
    print('Fixed Customer project')

# Fix Task model
old_task = '''        task_api = Task(
            id=f"task-api-{uuid.uuid4().hex[:8]}",
            organization_id=org.id,
            project_id=project_platform.id,
            title="Design API v2",
            rationale="Design new API version",
            status="in_progress",
            priority="high",
        )'''

new_task = '''        task_api = Task(
            id=f"task-api-{uuid.uuid4().hex[:8]}",
            organization_id=org.id,
            project_id=project_platform.id,
            title="Design API v2",
            description="Design new API version",
            status="in_progress",
            priority="high",
        )'''

if old_task in content:
    content = content.replace(old_task, new_task)
    print('Fixed API task')

old_task2 = '''        task_ui = Task(
            id=f"task-ui-{uuid.uuid4().hex[:8]}",
            organization_id=org.id,
            project_id=project_customer.id,
            title="Build Dashboard UI",
            rationale="Build customer dashboard",
            status="todo",
            priority="high",
        )'''

new_task2 = '''        task_ui = Task(
            id=f"task-ui-{uuid.uuid4().hex[:8]}",
            organization_id=org.id,
            project_id=project_customer.id,
            title="Build Dashboard UI",
            description="Build customer dashboard",
            status="todo",
            priority="high",
        )'''

if old_task2 in content:
    content = content.replace(old_task2, new_task2)
    print('Fixed UI task')

with codecs.open('tests/acceptance/test_production_deployment_dr_e2e.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('All description fixes applied')
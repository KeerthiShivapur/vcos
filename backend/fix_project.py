with open('tests/acceptance/adapters.py', 'r') as f:
    content = f.read()

# Fix Project creation - use 'code' instead of 'key'
content = content.replace(
    '''            project = Project(
                id=self._create_id("proj-"),
                organization_id=self.context.organization_id,
                name=project_names[i],
                key=project_names[i][:4].upper().replace(" ", ""),
                description=f"Project: {project_names[i]}",
                status="active",
                owner_id=employees[i % len(employees)].id if employees else self.context.caller.employee_id,
                start_date=datetime.now(timezone.utc).date(),
            )''',
    '''            project = Project(
                id=self._create_id("proj-"),
                organization_id=self.context.organization_id,
                name=project_names[i],
                code=project_names[i][:4].upper().replace(" ", ""),
                description=f"Project: {project_names[i]}",
                status="active",
                owner_id=employees[i % len(employees)].id if employees else self.context.caller.employee_id,
                start_date=datetime.now(timezone.utc).date(),
            )''')

with open('tests/acceptance/adapters.py', 'w') as f:
    f.write(content)

print('Fixed Project creation')
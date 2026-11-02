with open('tests/acceptance/adapters.py', 'r') as f:
    content = f.read()

# Fix Employee creation in CompanyProvisioningAdapter - use joining_date instead of start_date
content = content.replace(
    '''Employee(
                id=self._create_id("emp-"),
                organization_id=self.context.organization_id,
                user_id=user.id,
                department_id=dept.id,
                team_id=team.id if team else None,
                employee_number=f"E{self.context.run_id[:6]}{i:04d}",
                first_name=f"Employee",
                last_name=f"{i}",
                display_name=f"Employee {i}",
                email=f"employee-{i}-{self.context.run_id}@acceptance.test",
                start_date=datetime.now(timezone.utc).date(),
                
                employment_type="full_time",
            )''',
    '''Employee(
                id=self._create_id("emp-"),
                organization_id=self.context.organization_id,
                user_id=user.id,
                department_id=dept.id,
                team_id=team.id if team else None,
                employee_number=f"E{self.context.run_id[:6]}{i:04d}",
                first_name=f"Employee",
                last_name=f"{i}",
                display_name=f"Employee {i}",
                email=f"employee-{i}-{self.context.run_id}@acceptance.test",
                joining_date=datetime.now(timezone.utc).date(),
                
                employment_type="full_time",
            )''')

with open('tests/acceptance/adapters.py', 'w') as f:
    f.write(content)

print('Fixed Employee joining_date in provisioning adapter')
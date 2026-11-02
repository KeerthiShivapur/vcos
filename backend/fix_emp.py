with open('tests/acceptance/test_release_candidate_slice_2b.py', 'r') as f:
    content = f.read()

# Fix workforce component test - add required fields to employees
old = '''        emp1 = Employee(organization_id=org.id, user_id="user-1", display_name="Alice", department_id=dept.id)
        emp2 = Employee(organization_id=org.id, user_id="user-2", display_name="Bob", department_id=dept.id)'''

new = '''        emp1 = Employee(organization_id=org.id, user_id="user-1", employee_number="EMP001", first_name="Alice", email="alice@test.com", employment_type="full_time", status="active", timezone="UTC", expertise_score=0.0, profile_completion=0.0, display_name="Alice", department_id=dept.id)
        emp2 = Employee(organization_id=org.id, user_id="user-2", employee_number="EMP002", first_name="Bob", email="bob@test.com", employment_type="full_time", status="active", timezone="UTC", expertise_score=0.0, profile_completion=0.0, display_name="Bob", department_id=dept.id)'''

content = content.replace(old, new)

with open('tests/acceptance/test_release_candidate_slice_2b.py', 'w') as f:
    f.write(content)
print('Done')
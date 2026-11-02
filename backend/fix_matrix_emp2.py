with open('tests/acceptance/matrix_runner_real.py', 'r') as f:
    content = f.read()

# Fix Employee creation in matrix_runner_real.py - add required fields
content = content.replace(
    '''emp = Employee(
                id=f"ua-emp-{uuid.uuid4().hex[:8]}",
                organization_id=org.id,
                user_id=str(admin.id),
                employee_number=f"UA{profile_name[:3].upper()}{uuid.uuid4().hex[:4].upper()}",
                joining_date=datetime.now().date(),
                status="active",
                employment_type="full_time",
            )''',
    '''emp = Employee(
                id=f"ua-emp-{uuid.uuid4().hex[:8]}",
                organization_id=org.id,
                user_id=str(admin.id),
                employee_number=f"UA{profile_name[:3].upper()}{uuid.uuid4().hex[:4].upper()}",
                first_name="UA",
                last_name="Test",
                display_name="UA Test",
                email=f"ua-test-{uuid.uuid4().hex[:8]}@acceptance.test",
                joining_date=datetime.now().date(),
                status="active",
                employment_type="full_time",
            )''')

with open('tests/acceptance/matrix_runner_real.py', 'w') as f:
    f.write(content)

print('Fixed Employee in matrix_runner_real.py with required fields')
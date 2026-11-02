with open('tests/acceptance/matrix_runner_real.py', 'r') as f:
    content = f.read()

# Fix CallerAccess creation in matrix_runner_real.py
content = content.replace(
    '''from app.intelligence.company_context import CallerAccess
        return CallerAccess(
            organization_id=org.id,
            user=admin,
            employee=emp,
            roles=["admin"],
            permissions=["*"],
            accessible_org_ids=[org.id],
        )''',
    '''from app.intelligence.company_context import CallerAccess
        return CallerAccess(
            organization_id=org.id,
            user_id=str(admin.id),
            employee_id=emp.id,
            org_wide=True,
            anchored_scope_ids=frozenset(),
            ancestry_scope_ids=frozenset(),
            visible_scope_ids=frozenset(),
            project_ids=frozenset(),
            member_conversation_ids=frozenset(),
            links={},
        )''')

with open('tests/acceptance/matrix_runner_real.py', 'w') as f:
    f.write(content)

print('Fixed CallerAccess in matrix_runner_real.py')
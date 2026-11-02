with open('tests/test_gate6f_epistemic_integrity.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix RoleAssignment to PersonRoleAssignment
content = content.replace('from app.models.governance import RoleAssignment', 'from app.models.people_intelligence import PersonRoleAssignment')
content = content.replace('role_assignment = RoleAssignment(', 'role_assignment = PersonRoleAssignment(')

with open('tests/test_gate6f_epistemic_integrity.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Fixed RoleAssignment to PersonRoleAssignment')
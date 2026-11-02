with open('tests/acceptance/adapters.py', 'r') as f:
    content = f.read()

# Fix UserRole creation - remove assigned_by - match exact formatting
content = content.replace(
    '''user_role = UserRole(
                    id=self._create_id("ur-"),
                    user_id=user.id,
                    role_id=role.id,
                    organization_id=self.context.organization_id,
                    
                    scope_id=self.context.organization_id,
                    assigned_by=self.context.caller.employee_id,
                    status="active",
                )''',
    '''user_role = UserRole(
                    id=self._create_id("ur-"),
                    user_id=user.id,
                    role_id=role.id,
                    organization_id=self.context.organization_id,
                    
                    scope_id=self.context.organization_id,
                    status="active",
                )''')

with open('tests/acceptance/adapters.py', 'w') as f:
    f.write(content)

print('Fixed UserRole')
with open('tests/acceptance/adapters.py', 'r') as f:
    content = f.read()

# Fix UserRole creation in IdentityAdapter - remove assigned_by
content = content.replace(
    '''UserRole(
            id=self._create_id("ur-"),
            user_id=emp.user_id,
            role_id=new_role.id,
            organization_id=self.context.organization_id,
            
            scope_id=self.context.organization_id,
            assigned_by=self.context.caller.employee_id,
            
        )''',
    '''UserRole(
            id=self._create_id("ur-"),
            user_id=emp.user_id,
            role_id=new_role.id,
            organization_id=self.context.organization_id,
            
            scope_id=self.context.organization_id,
            
        )''')

with open('tests/acceptance/adapters.py', 'w') as f:
    f.write(content)

print('Fixed UserRole in identity adapter')
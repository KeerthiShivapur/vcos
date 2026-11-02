with open('tests/acceptance/adapters.py', 'r') as f:
    content = f.read()

# Fix Role creation - remove status field
content = content.replace(
    '''            role = Role(
                id=self._create_id("role-"),
                organization_id=self.context.organization_id,
                name=role_name,
                code=role_key,
                description=f"{role_name} role",
                status="active",
            )''',
    '''            role = Role(
                id=self._create_id("role-"),
                organization_id=self.context.organization_id,
                name=role_name,
                code=role_key,
                description=f"{role_name} role",
            )''')

with open('tests/acceptance/adapters.py', 'w') as f:
    f.write(content)

print('Fixed Role status')
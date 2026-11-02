with open('tests/acceptance/adapters.py', 'r') as f:
    content = f.read()

# Fix UserRole - remove status field
content = content.replace(
    'status="active",',
    ''
)

# Fix Project in work adapter - use start_date
content = content.replace(
    'joining_date=datetime.now(timezone.utc).date(),',
    'start_date=datetime.now(timezone.utc).date(),'
)

with open('tests/acceptance/adapters.py', 'w') as f:
    f.write(content)

print('Fixed UserRole status and Project')
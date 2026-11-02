with open('tests/acceptance/matrix_runner_real.py', 'r') as f:
    content = f.read()

# Add Employee import
content = content.replace(
    'from sqlalchemy import select\nfrom sqlalchemy.ext.asyncio import AsyncSession',
    'from sqlalchemy import select\nfrom sqlalchemy.ext.asyncio import AsyncSession\nfrom app.models import Employee, User, Organization'
)

with open('tests/acceptance/matrix_runner_real.py', 'w') as f:
    f.write(content)

print('Added Employee import')
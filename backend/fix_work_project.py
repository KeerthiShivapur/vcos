with open('tests/acceptance/adapters.py', 'r') as f:
    content = f.read()

# Fix Project in work adapter - use start_date instead of joining_date
content = content.replace(
    'joining_date=datetime.now(timezone.utc).date(),',
    'start_date=datetime.now(timezone.utc).date(),'
)

with open('tests/acceptance/adapters.py', 'w') as f:
    f.write(content)

print('Fixed Project start_date in work adapter')
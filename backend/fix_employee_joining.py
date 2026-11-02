with open('tests/acceptance/adapters.py', 'r') as f:
    content = f.read()

# Fix Employee - use joining_date instead of start_date
content = content.replace(
    'start_date=datetime.now(timezone.utc).date(),',
    'joining_date=datetime.now(timezone.utc).date(),'
)

with open('tests/acceptance/adapters.py', 'w') as f:
    f.write(content)

print('Fixed Employee joining_date')
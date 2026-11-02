with open('tests/acceptance/adapters.py', 'r') as f:
    content = f.read()

# Fix the revocation state - use 'rejected' instead of 'revoked'
content = content.replace(
    'delegation.state = "revoked"',
    'delegation.state = "rejected"'
)

with open('tests/acceptance/adapters.py', 'w') as f:
    f.write(content)

print('Fixed revocation state')
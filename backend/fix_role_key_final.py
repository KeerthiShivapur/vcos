with open('tests/acceptance/adapters.py', 'r') as f:
    content = f.read()

# Fix role.key -> role.code
content = content.replace('r.key == "admin"', 'r.code == "admin"')
content = content.replace('r.key == "contributor"', 'r.code == "contributor"')
content = content.replace('r.key == "lead"', 'r.code == "lead"')

# Fix policy.key -> policy.approval_type
content = content.replace('policy.key', 'policy.approval_type')

with open('tests/acceptance/adapters.py', 'w') as f:
    f.write(content)

print('Fixed role.key and policy.key')
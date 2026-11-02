with open('tests/acceptance/adapters.py', 'r') as f:
    content = f.read()

# Fix SecurityAdapter - change observation_type from 'external_integration' to 'external_operation'
content = content.replace(
    'observation_type="external_integration"',
    'observation_type="external_operation"'
)

with open('tests/acceptance/adapters.py', 'w') as f:
    f.write(content)

print('Fixed observation_type')
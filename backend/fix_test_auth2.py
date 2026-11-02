with open('tests/acceptance/adapters.py', 'r') as f:
    content = f.read()

# Fix _test_authorization - use policy.id instead of project.id
content = content.replace(
    'source_event_id=f"{self.context.run_id}-dec-{project.id}",',
    'source_event_id=f"{self.context.run_id}-dec-{policy.id}",'
)

with open('tests/acceptance/adapters.py', 'w') as f:
    f.write(content)

print('Fixed _test_authorization')
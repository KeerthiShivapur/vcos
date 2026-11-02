with open('tests/acceptance/adapters.py', 'r') as f:
    content = f.read()

# Fix _create_decisions - use project.id instead of policy.id
content = content.replace(
    'source_event_id=f"{self.context.run_id}-dec-{policy.id}",',
    'source_event_id=f"{self.context.run_id}-dec-{project.id}",'
)

with open('tests/acceptance/adapters.py', 'w') as f:
    f.write(content)

print('Fixed _create_decisions')
with open('tests/acceptance/adapters.py', 'r') as f:
    content = f.read()

# Fix the idx usage - use enumerate or policy.id
content = content.replace(
    'source_event_id=f"{self.context.run_id}-dec-{idx}"',
    'source_event_id=f"{self.context.run_id}-dec-{policy.id}"'
)

with open('tests/acceptance/adapters.py', 'w') as f:
    f.write(content)

print('Fixed idx in governance adapter')
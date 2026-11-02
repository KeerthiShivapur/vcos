with open('tests/acceptance/adapters.py', 'r') as f:
    content = f.read()

# Find the problematic idx usage
idx = content.find('source_event_id=f"{self.context.run_id}-dec-{idx}"')
if idx >= 0:
    print(repr(content[max(0,idx-200):idx+200]))
with open('tests/acceptance/adapters.py', 'r') as f:
    content = f.read()

# Find the CompanyAuthorization creation with idx
idx = content.find('source_event_id=f"{self.context.run_id}-dec-{idx}"')
if idx >= 0:
    # Find the start of this block - look for the loop
    start = content.rfind('for ', 0, idx)
    if start == -1:
        start = content.rfind('for idx', 0, idx)
    print(repr(content[max(0,start-200):idx+200]))
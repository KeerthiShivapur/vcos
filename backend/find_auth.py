with open('tests/acceptance/adapters.py', 'r') as f:
    content = f.read()

# Find the problematic CompanyAuthorization
idx = content.find('action="delegate"')
if idx >= 0:
    # Find the start of this CompanyAuthorization
    start = content.rfind('CompanyAuthorization(', 0, idx)
    print(repr(content[start:idx+500]))
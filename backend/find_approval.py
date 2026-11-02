with open('tests/acceptance/adapters.py', 'r') as f:
    content = f.read()

# Find ApprovalPolicy creation
idx = content.find('ApprovalPolicy(')
if idx >= 0:
    print(repr(content[idx:idx+500]))
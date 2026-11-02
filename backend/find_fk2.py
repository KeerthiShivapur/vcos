with open('app/models/canonical_reliability.py', 'r') as f:
    content = f.read()

# Print context around the first match (ExternalUnknownState)
print(content[25300:25700])
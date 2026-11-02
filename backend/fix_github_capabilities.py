with open('app/services/provider_adapters.py', 'r') as f:
    content = f.read()

# Update GitHubAdapter outbound_capabilities to only include "read"
old = '''    outbound_capabilities = ["create", "read", "update", "delete"]'''

new = '''    outbound_capabilities = ["read"]'''

content = content.replace(old, new)

with open('app/services/provider_adapters.py', 'w') as f:
    f.write(content)
print('Fixed')
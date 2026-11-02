with open('app/intelligence/governed_commitment_engine.py', 'r') as f:
    content = f.read()
import re
# Find authorization_type values
types = re.findall(r'authorization_type\s*=\s*"([^"]+)"', content)
print(set(types))
types2 = re.findall(r'Authorization.*type\s*=\s*"([^"]+)"', content)
print(set(types2))
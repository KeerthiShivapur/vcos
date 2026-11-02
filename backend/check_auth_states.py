with open('app/intelligence/governed_commitment_engine.py', 'r') as f:
    content = f.read()
import re
states = re.findall(r'auth\.state\s*=\s*"([^"]+)"', content)
print(set(states))
states2 = re.findall(r'Authorization.*state\s*=\s*"([^"]+)"', content)
print(set(states2))
# Also check for CompanyAuthorization state values
states3 = re.findall(r'CompanyAuthorization.*state\s*=\s*"([^"]+)"', content)
print(set(states3))
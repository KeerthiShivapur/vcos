with open('app/intelligence/governed_commitment_engine.py', 'r') as f:
    content = f.read()
import re
states = re.findall(r'"(proposed|pending_authorization|authorized|fulfilled|superseded|blocked|expired)"', content)
print(set(states))
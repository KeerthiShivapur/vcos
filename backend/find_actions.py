import re

with open('tests/acceptance/scenario_builder.py', 'r') as f:
    content = f.read()

actions = re.findall(r'action\s*[:=]\s*["\']([^"\']+)["\']', content)
print('Actions:', set(actions))
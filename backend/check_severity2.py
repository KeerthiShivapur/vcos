import re
with open('app/intelligence/adaptive_planning_engine.py', 'r') as f:
    content = f.read()
for m in re.finditer(r'severity\s*=\s*["\']([^"\']+)["\']', content):
    print(m.group(1))
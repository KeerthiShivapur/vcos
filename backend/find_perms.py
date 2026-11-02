with open('app/services/permission_service.py', 'r', encoding='utf-8') as f:
    content = f.read()

import re
perms = re.findall(r'"([a-z_]+:[a-z_]+)"', content)
unique_perms = sorted(set(perms))
for p in unique_perms:
    if 'evidence' in p or 'decision' in p:
        print(p)
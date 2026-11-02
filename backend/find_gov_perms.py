with open('app/services/permission_service.py', 'r', encoding='utf-8') as f:
    content = f.read()

import re
perms = re.findall(r'"(governance:[a-z_]+)"', content)
print(sorted(set(perms)))
import re
with open('openapi2.json', 'r', encoding='utf-8', errors='ignore') as f:
    content = f.read()
paths = re.findall(r'"(/api/v1/[^"]+)":', content)
auth_paths = [p for p in paths if 'auth' in p.lower()]
print('Auth paths found:', auth_paths)
print('Total paths:', len(paths))
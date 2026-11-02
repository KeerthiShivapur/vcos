with open('app/services/permission_service.py', 'r', encoding='utf-8') as f:
    content = f.read()

idx = content.find('"ceo":')
if idx >= 0:
    print(content[idx:idx+3000])
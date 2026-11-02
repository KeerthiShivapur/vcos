with open('app/models/knowledge.py', 'r', encoding='utf-8') as f:
    content = f.read()

idx = content.find('class KnowledgeClaim')
if idx >= 0:
    print(content[idx:idx+1000])
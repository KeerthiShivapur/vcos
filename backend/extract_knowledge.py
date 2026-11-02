with open('app/models/knowledge.py', 'rb') as f:
    content = f.read()

idx = content.find(b'class KnowledgeClaim')
if idx >= 0:
    with open('output.txt', 'wb') as out:
        out.write(content[idx:idx+2000])
    print("Written to output.txt")
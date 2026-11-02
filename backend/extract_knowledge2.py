with open('app/models/knowledge.py', 'rb') as f:
    content = f.read()

idx = content.find(b'class KnowledgeEvidence')
if idx >= 0:
    with open('output2.txt', 'wb') as out:
        out.write(content[idx:idx+1500])
    print("Written to output2.txt")
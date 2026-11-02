with open('app/services/permission_service.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Find CEO permissions
idx = content.find('"ceo":')
if idx >= 0:
    # Find the closing ]
    bracket_count = 0
    start = idx
    for i in range(idx, len(content)):
        if content[i] == '[':
            bracket_count += 1
        elif content[i] == ']':
            bracket_count -= 1
            if bracket_count == 0:
                print(content[start:i+1])
                break
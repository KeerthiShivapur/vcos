with open('D:\\vcos1\\workspace\\vcos\\backend\\tests\\scale\\postgres\\diagnostics.py', 'rb') as f:
    content = f.read()

# Fix the missing closing parenthesis in replication.append()
old = b'            }\n        return {"replication_slots": replication}'
new = b'            })\n        return {"replication_slots": replication}'

content = content.replace(old, new)

with open('D:\\vcos1\\workspace\\vcos\\backend\\tests\\scale\\postgres\\diagnostics.py', 'wb') as f:
    f.write(content)

print('Fixed!')
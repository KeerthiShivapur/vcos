with open('tests/acceptance/adapters.py', 'rb') as f:
    content = f.read()

# Replace CRLF with LF
content = content.replace(b'\r\n', b'\n')

with open('tests/acceptance/adapters.py', 'wb') as f:
    f.write(content)

print('Fixed line endings')
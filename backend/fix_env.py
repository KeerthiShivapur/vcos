with open('D:\\vcos1\\workspace\\vcos\\backend\\tests\\scale\\postgres\\environment.py', 'rb') as f:
    lines = f.read().split(b'\n')

# Fix line 877 (index 877) - add the method body
lines[877] = b'        raise NotImplementedError("Use async session for container environment")'

with open('D:\\vcos1\\workspace\\vcos\\backend\\tests\\scale\\postgres\\environment.py', 'wb') as f:
    f.write(b'\n'.join(lines))

print('Fixed!')
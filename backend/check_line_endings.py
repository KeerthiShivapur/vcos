with open('tests/acceptance/adapters.py', 'rb') as f:
    content = f.read()

# Check for CRLF
if b'\r\n' in content:
    print('Found CRLF')
    print(f'CRLF count: {content.count(b"\r\n")}')
    print(f'LF count: {content.count(b"\n") - content.count(b"\r\n")}')
else:
    print('No CRLF')
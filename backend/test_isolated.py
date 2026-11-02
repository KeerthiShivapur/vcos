# Test the docstring in isolation
test_code = '''
        """Get user's workspace personalization settings."""
'''
print('Test code:', repr(test_code))
try:
    compile(test_code, '<test>', 'exec')
    print('Isolated docstring: OK')
except SyntaxError as e:
    print(f'Isolated error: {e.msg}')

# Test with exact indentation from file
test_code2 = '        """Get user\'s workspace personalization settings."""\n'
print('Test with indent:', repr(test_code2))
try:
    compile(test_code2, '<test>', 'exec')
    print('With indent: OK')
except SyntaxError as e:
    print(f'With indent error: {e.msg}')

# Test the exact line from file
line = '        """Get user\'s workspace personalization settings."""\r'
print('Exact line from file:', repr(line))
try:
    compile(line, '<test>', 'exec')
    print('Exact line: OK')
except SyntaxError as e:
    print(f'Exact line error: {e.msg}')
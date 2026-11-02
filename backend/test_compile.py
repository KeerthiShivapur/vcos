code = '"""Get user\'s workspace personalization settings."""'
print('Code:', repr(code))
try:
    compile(code, '<string>', 'exec')
    print('Compile successful!')
except SyntaxError as e:
    print(f'SyntaxError: {e.msg} at line {e.lineno}, offset {e.offset}')
    print(f'Line: {e.text}')
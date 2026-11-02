line = b'        """Get user\'s workspace personalization settings."""'
print('Line bytes:', line)
print('Hex:', line.hex())
try:
    compile(line, '<string>', 'exec')
    print('Compile successful!')
except SyntaxError as e:
    print(f'SyntaxError: {e.msg} at offset {e.offset}')
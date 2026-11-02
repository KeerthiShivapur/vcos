# Test if triple quotes work in this environment
test_code = '''
def test():
    """This is a docstring."""
    pass
'''

try:
    compile(test_code, '<test>', 'exec')
    print('Triple quotes work fine')
except SyntaxError as e:
    print(f'SyntaxError: {e.msg}')
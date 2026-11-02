with open('tests/acceptance/adapters.py', 'r') as f:
    content = f.read()

# Find the _create_outcomes method
idx = content.find('_create_outcomes')
if idx >= 0:
    # Find the next method or class
    next_method = content.find('async def ', idx + 20)
    if next_method == -1:
        next_method = content.find('class ', idx + 20)
    if next_method == -1:
        next_method = len(content)
    print(repr(content[idx:next_method]))
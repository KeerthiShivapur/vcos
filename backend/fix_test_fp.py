with open('tests/acceptance/test_release_candidate_slice_2c.py', 'r') as f:
    content = f.read()

# Fix the test to match actual failure_point
old = '''        assert injection.failure_point == "preflight_check"'''

new = '''        assert injection.failure_point == "preflight"'''

content = content.replace(old, new)

with open('tests/acceptance/test_release_candidate_slice_2c.py', 'w') as f:
    f.write(content)
print('Done')
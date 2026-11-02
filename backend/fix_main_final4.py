with open('tests/acceptance/test_release_candidate_hardening_e2e.py', 'r') as f:
    content = f.read()

# Find all occurrences
search = 'if __name__ == "__main__":'
idx1 = content.find(search)
idx2 = content.find(search, idx1 + 1)

# Replace from second occurrence to end with just the main block
if idx2 > 0:
    content = content[:idx2] + 'if __name__ == "__main__":\n    pytest.main([__file__, "-v"])'
    with open('tests/acceptance/test_release_candidate_hardening_e2e.py', 'w') as f:
        f.write(content)
    print('Fixed')
else:
    print('Not found')
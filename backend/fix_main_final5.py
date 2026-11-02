with open('tests/acceptance/test_release_candidate_hardening_e2e.py', 'r') as f:
    content = f.read()

# The problem: content has "if __name__...pytest...if __name__...pytest..."
# We need to keep only the first one
bad = 'if __name__ == "__main__":\n    pytest.main([__file__, "-v"])if __name__ == "__main__":\n    pytest.main([__file__, "-v"])'
good = 'if __name__ == "__main__":\n    pytest.main([__file__, "-v"])'

if bad in content:
    content = content.replace(bad, good)
    with open('tests/acceptance/test_release_candidate_hardening_e2e.py', 'w') as f:
        f.write(content)
    print('Fixed')
else:
    print('Pattern not found')
with open('tests/acceptance/test_release_candidate_hardening_e2e.py', 'r') as f:
    content = f.read()

# Fix the duplicated __main__ block
old_code = '''if __name__ == "__main__":
if __name__ == "__main__":
    pytest.main([__file__, "-v"])'''

new_code = 'if __name__ == "__main__":\n    pytest.main([__file__, "-v"])'

content = content.replace(
    'if __name__ == "__main__":\nif __name__ == "__main__":\n    pytest.main([__file__, "-v"])',
    'if __name__ == "__main__":\n    pytest.main([__file__, "-v"])'
)

with open('tests/acceptance/test_release_candidate_hardening_e2e.py', 'w') as f:
    f.write(content)
print('Done')
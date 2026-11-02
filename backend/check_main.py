with open('tests/acceptance/test_release_candidate_hardening_e2e.py', 'r') as f:
    content = f.read()

# Find all occurrences
search = 'if __name__ == "__main__":'
idx1 = content.find(search)
idx2 = content.find(search, idx1 + 1)
print('First at', idx1, 'second at', idx2)
print(repr(content[idx1:idx2+50]))
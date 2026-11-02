with open('tests/acceptance/test_release_candidate_hardening_e2e.py', 'r') as f:
    content = f.read()

search = 'if __name__ == "__main__":'
idx1 = content.find(search)
idx2 = content.find(search, idx1 + 1)
print('First at', idx1, 'second at', idx2)
print('Length:', len(content))
print(repr(content[idx1:idx1+100]))
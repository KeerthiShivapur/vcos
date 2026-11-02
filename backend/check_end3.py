with open('tests/acceptance/test_release_candidate_hardening_e2e.py', 'r') as f:
    content = f.read()

idx = content.rfind('if __name__ == "__main__"')
if idx >= 0:
    print(content[idx-200:idx+200])
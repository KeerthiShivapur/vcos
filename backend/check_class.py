with open('tests/acceptance/test_release_candidate_hardening_e2e.py', 'r') as f:
    content = f.read()

idx = content.find('class TestReleaseCandidateHardeningE2E')
idx2 = content.find('if __name__ == "__main__"')
if idx2 == -1:
    idx2 = len(content)
print(content[idx:idx2])
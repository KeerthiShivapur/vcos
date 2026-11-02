with open('tests/acceptance/test_release_candidate_slice_2b.py', 'r') as f:
    content = f.read()

# Remove fingerprint parameter from all CompanyDecision creations
content = content.replace(', fingerprint=_gen_fp())', ')')
content = content.replace(', fingerprint=_gen_fp(),', ',')

with open('tests/acceptance/test_release_candidate_slice_2b.py', 'w') as f:
    f.write(content)
print('Done')
with open('tests/acceptance/test_release_candidate_hardening_e2e.py', 'r') as f:
    content = f.read()

# Find the concurrent mutations section
idx = content.find('Run 5 concurrent mutations')
if idx >= 0:
    # Find the line before the concurrent mutations section
    lines = content[:idx].split('\n')
    for i, line in enumerate(reversed(lines)):
        if 'logger.info' in line and 'Concurrent' in line:
            print(f'Found at line {len(lines) - i - 1}')
            break
    print('...')
    print(content[idx-200:idx+300])

with open('tests/acceptance/test_release_candidate_hardening_e2e.py', 'w') as f:
    f.write(content)
print('Done')
with open('tests/acceptance/test_release_candidate_hardening_e2e.py', 'r') as f:
    content = f.read()

# Find the position before "if __name__ == \"__main__\":"
idx = content.find('if __name__ == "__main__":')
if idx < 0:
    print("Could not find __main__")
    exit(1)

# Find the end of the test method
idx2 = content.rfind('logger.info("=== RELEASE CANDIDATE HARDENING E2E: COMPLETE ===")')
if idx2 < 0:
    idx2 = content.find('if __name__ == "__main__"')
    if idx2 < 0:
        idx2 = len(content)

# Find the end of the test method (before the if __name__ == "__main__")
idx2 = content.find('logger.info("=== RELEASE CANDIDATE HARDENING E2E: COMPLETE =====")')
if idx2 >= 0:
    idx2 = content.find('\n', idx2)
    idx2 = content.find('\n', idx2 + 1)
    idx2 = content.find('\n', idx2 + 1)

print(f"Found end at index: {idx2}")
print(content[idx2-200:idx2+200])
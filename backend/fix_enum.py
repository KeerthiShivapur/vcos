with open('app/models/release.py', 'r') as f:
    content = f.read()

# Fix duplicate enum - remove the duplicate
content = content.replace(
    'RECOVERY_VALIDATION_FAILED = "recovery_validation_failed"\n    ROLLED_BACK = "rolled_back"',
    'ROLLED_BACK = "rolled_back"'
)

with open('app/models/release.py', 'w') as f:
    f.write(content)
print('Done')
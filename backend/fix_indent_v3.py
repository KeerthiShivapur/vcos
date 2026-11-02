with open('app/services/onboarding_service.py', 'r') as f:
    lines = f.readlines()

# Check lines around 345
for i in range(340, 360):
    if i < len(lines):
        print(f'{i+1}: {repr(lines[i])}')

# Fix line 345 (index 344)
if len(lines) > 344 and lines[344].startswith('        self._active_onboardings'):
    # Check if it's over-indented
    if lines[344].startswith('            '):
        lines[344] = '        ' + lines[344].lstrip()
        print(f'Fixed line 345: {repr(lines[344])}')

with open('app/services/onboarding_service.py', 'w') as f:
    f.writelines(lines)
print('Fixed')
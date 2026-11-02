# This script fixes the ScaleRunnerLegacy wrapper class methods to use self._runner instead of self

import re

with open(r'D:\vcos1\workspace\vcos\backend\tests\scale\postgres\scale_runner.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Replace all occurrences of self.environment with self._runner.environment
# self.profile -> self._runner.profile
# self.environment -> self._runner.environment
# self.profile -> self._runner.profile

replacements = [
    ('self.environment.', 'self._runner.environment.'),
    ('self.profile.', 'self._runner.profile.'),
    ('self.profile.name', 'self._runner.profile.name'),
    ('self.profile.employee_count', 'self._runner.profile.employee_count'),
    ('self.profile.name', 'self._runner.profile.name'),
]

for old, new in replacements:
    content = content.replace(old, new)

with open(r'D:\vcos1\workspace\vcos\backend\tests\scale\postgres\scale_runner.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Fixed wrapper class references')
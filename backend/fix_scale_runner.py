with open(r'D:\vcos1\workspace\vcos\backend\tests\scale\postgres\scale_runner.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Find the duplicate line and the inserted method
lines = content.split('\n')
new_lines = []
skip = False

for i, line in enumerate(content.split('\n')):
    if 'self._state_machine.transition(ScaleRunState.COMPLETED)' in line and line.strip() == 'self._state_machine.transition(ScaleRunState.COMPLETED)':
        # Check if this is the duplicate (around line 290)
        if len([l for l in content.split('\n')[:content.split('\n').index(line)] if 'self._state_machine.transition(ScaleRunState.COMPLETED)' in l]) > 1:
            continue
        new_lines.append(line)
    elif 'async def _phase_cleanup_existing_data(self):' in line:
        # Skip the inserted method
        skip = True
        continue
    elif skip and line.strip() == '"""Phase 1: Environment resolution and comprehensive preflight."""':
        # End of the inserted method
        skip = False
        new_lines.append(line)
    elif skip:
        continue
    else:
        new_lines.append(line)

new_content = '\n'.join(new_lines)
with open(r'D:\vcos1\workspace\vcos\backend\tests\scale\postgres\scale_runner.py', 'w', encoding='utf-8') as f:
    f.write(new_content)
print('Fixed')
with open('D:\\vcos1\\workspace\\vcos\\backend\\tests\\scale\\postgres\\diagnostics.py', 'rb') as f:
    content = f.read()
lines = content.split(b'\n')

# Remove the duplicate line at index 130 (line 131)
# Line 131 has: checkpoint_completion_target=get_setting("checkpoint_completion_target"),
# Keep the one at line 125, remove the duplicate at line 131
new_lines = []
for i, line in enumerate(lines):
    if not (i == 130 and line == b'            checkpoint_completion_target=get_setting("checkpoint_completion_target"),'):
        new_lines.append(line)

with open('D:\\vcos1\\workspace\\vcos\\backend\\tests\\scale\\postgres\\diagnostics.py', 'wb') as f:
    f.write(b'\n'.join(new_lines))

print('Fixed duplicate checkpoint_completion_target!')
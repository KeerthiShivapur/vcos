with open('tests/acceptance/test_complete_company_e2e.py', 'r') as f:
    lines = f.readlines()

# Find the class
class_start = None
for i, line in enumerate(lines):
    if 'class TestE2EJourneyIntegration:' in line:
        class_start = i
        break

# Find the next class
next_class = None
for i in range(class_start + 1, len(lines)):
    if lines[i].strip().startswith('class '):
        next_class = i
        break
if next_class is None:
    next_class = len(lines)

print(f'Class from {class_start} to {next_class}')

# Find the last complete method before the broken one
last_method_start = None
for i in range(class_start, next_class):
    if 'async def test_' in lines[i] and 'test_five_extraordinary_capabilities' not in lines[i]:
        last_method_start = i

print(f'Last good method at line: {last_method_start}')

# Find the end of the last good method
method_end = None
for i in range(last_method_start + 1, len(lines)):
    if lines[i].strip() and not lines[i].startswith(' ') and not lines[i].startswith('\t'):
        method_end = i
        break
if method_end is None:
    method_end = len(lines)

print(f'Last good method ends at: {method_end}')

# The broken method starts after the last good method
broken_start = last_method_end = None
for i in range(last_method_start, len(lines)):
    if 'test_five_extraordinary_capabilities' in lines[i] and 'async def' in lines[i]:
        broken_start = i
        break

print(f'Broken method starts at: {broken_start}')

# Find where the broken method ends (next method or class)
broken_end = None
for i in range(broken_start + 1, len(lines)):
    if lines[i].strip() and not lines[i].startswith(' ') and not lines[i].startswith('\t'):
        broken_end = i
        break
if broken_end is None:
    broken_end = len(lines)

print(f'Broken method from {broken_start} to {broken_end}')

# Now we need to replace from the last good method's end to the broken method's end
# with a correct implementation

# Find the end of the last good method
method_end = None
for i in range(last_method_start + 1, len(lines)):
    if lines[i].strip() and not lines[i].startswith(' ') and not lines[i].startswith('\t'):
        method_end = i
        break
if method_end is None:
    method_end = len(lines)

# The insertion point is after the last good method
insert_pos = method_end

print(f'Inserting at position: {insert_pos}')

# Read the entire file content
with open('tests/acceptance/test_complete_company_e2e.py', 'r') as f:
    content = f.read()

# Find the class
class_start = content.find('class TestE2EJourneyIntegration:')
next_class = content.find('\nclass ', class_start + 1)
if next_class == -1:
    next_class = len(content)

# Find the last complete method before the broken one
class_content = content[class_start:next_class]
last_method = class_content.rfind('async def test_')
last_method_abs = class_start + last_method

# Find end of that method
method_end = content.find('\n    async def test_', class_start + last_method + 1)
if method_end == -1:
    method_end = content.find('\nclass ', class_start + last_method + 1)
if method_end == -1:
    method_end = class_start + len(content[class_start:next_class])

print(f'Insert at: {method_end}')

# The last good method ends at method_end
# We need to insert our new method after method_end and before next_class
# But we need to remove the broken method first

# Find the broken method
broken_start = content.find('async def test_five_extraordinary_capabilities(self, db_session, provisioned_company):')
if broken_start == -1:
    print('Method not found!')
else:
    print(f'Broken method at: {broken_start}')
    # Find end of broken method
    broken_end = content.find('\n    async def test_', broken_start + 1)
    if broken_end == -1:
        broken_end = content.find('\nclass ', broken_start + 1)
    if broken_end == -1:
        broken_end = len(content)
    print(f'Broken method from {broken_start} to {broken_end}')

# Remove broken method and insert correct one
new_content = content[:decorator_start] + new_method + content[next_class:]

# Wait, we need to find the decorator for the broken method
broken_decorator = content.rfind('@pytest.mark.asyncio', 0, broken_start)
print(f'Broken decorator at: {broken_decorator}')

# Remove from broken_decorator to broken_end
# Insert new method at decorator_start
new_content = content[:decorator_start] + new_method + content[next_class:]

with open('tests/acceptance/test_complete_company_e2e.py', 'w') as f:
    f.write(new_content)

print('Fixed')
"
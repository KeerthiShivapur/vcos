with open('tests/conftest.py', 'r') as f:
    lines = f.readlines()

# Find the register_org function and fix the email default
for i, line in enumerate(lines):
    if 'async def register_org' in line:
        print(f'Found at line {i+1}: {line.rstrip()}')
        # Find the email parameter line
        for j in range(i, min(i+10, len(lines))):
            if 'email=' in lines[j]:
                print(f'Email param at line {j+1}: {lines[j].rstrip()}')
                lines[j] = lines[j].replace('email="owner@acme.test.co"', 'email=f"owner-{uuid.uuid4().hex[:8]}@acme.test.co"')
                print(f'Fixed line {j+1}: {lines[j].rstrip()}')
                break
        break

with open('tests/conftest.py', 'w') as f:
    f.writelines(lines)

print('Fixed register_org email default')
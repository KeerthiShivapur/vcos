# Read the file
with open('tests/acceptance/test_deployment_dr_production_verification.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Find the first "COMPLETE" section end (line 1083-1084)
# Then delete everything until the next test function starts at line 2032

# Line numbers are 0-indexed in Python list
# The first COMPLETE is around index 1082-1083
# The duplicate starts at index 1085
# The next test starts at index 2031

# Find the end of first test (the return statement)
end_idx = None
for i in range(1080, len(lines)):
    if '"organization_id": org.id,' in lines[i] and i > 1080:
        # Find the end of the return dict
        for j in range(i, len(lines)):
            if '        }' in lines[j] and lines[j].strip() == '}':
                end_idx = j
                break
        break

if end_idx is None:
    print("Could not find end of first test")
    exit(1)

# Find the start of next test function
next_test_idx = None
for i in range(end_idx + 1, len(lines)):
    if 'async def test_multi_tenant_backup_restore_isolation_real_pg' in lines[i]:
        next_test_idx = i
        break

if next_test_idx is None:
    print("Could not find next test")
    exit(1)

print(f"First test ends at line {end_idx + 1}")
print(f"Next test starts at line {next_test_idx + 1}")

# Keep lines 0 to end_idx, then lines next_test_idx onwards
new_lines = lines[:end_idx + 1] + ['\n'] + lines[next_test_idx:]

with open('tests/acceptance/test_deployment_dr_production_verification.py', 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print(f"Fixed: removed {next_test_idx - end_idx - 1} duplicate lines")
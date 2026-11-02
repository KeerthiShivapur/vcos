# Read the file
with open('tests/acceptance/test_deployment_dr_production_verification.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Find the actual end of the first test - the return statement with proper indentation (8 spaces)
end_idx = None
for i in range(1080, len(lines)):
    # Look for the actual return with 8-space indent (not 12)
    if lines[i].startswith('        return {') and i > 1080:
        # Find the closing }
        for j in range(i, len(lines)):
            if lines[j].strip() == '}' and j > i:
                end_idx = j
                break
        break

if end_idx is None:
    print("Could not find end of first test")
    # Try another approach - find "organization_id" in return
    for i in range(1080, len(lines)):
        if '"organization_id": org.id,' in lines[i] and lines[i].startswith('        '):
            # Check if it's the real one (8 spaces)
            if len(lines[i]) - len(lines[i].lstrip()) == 8:
                for j in range(i, len(lines)):
                    if lines[j].strip() == '}' and j > i:
                        end_idx = j
                        break
                break

if end_idx is None:
    print("Could not find end of first test with alternative method")
    exit(1)

print("First test (real) ends at line " + str(end_idx + 1))

# The duplicate starts at line 1085 (index 1085)
# We need to keep lines 0 to 1084 (the first COMPLETE log), then skip to after end_idx

new_lines = lines[:1085] + ['\n'] + lines[end_idx + 1:]

with open('tests/acceptance/test_deployment_dr_production_verification.py', 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print("Fixed: kept lines 0-1084, removed 1085-" + str(end_idx) + ", kept from " + str(end_idx + 1))
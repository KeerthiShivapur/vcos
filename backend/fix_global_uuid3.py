import codecs

with codecs.open('tests/acceptance/test_production_deployment_dr_e2e.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Find the function definition line
func_start_idx = -1
for i, line in enumerate(lines):
    if 'async def test_complete_production_dr_lifecycle' in line:
        func_start_idx = i
        break

if func_start_idx == -1:
    print('Function not found')
else:
    print(f'Function at line {func_start_idx + 1}')
    
    # Find the docstring end and the first code line
    docstring_end = -1
    for i in range(func_start_idx + 1, len(lines)):
        if 'org = production_company["organization"]' in lines[i]:
            docstring_end = i
            break
    
    if docstring_end == -1:
        print('Could not find org assignment')
    else:
        print(f'Found org assignment at line {docstring_end + 1}')
        # Insert global uuid before the org assignment
        lines.insert(docstring_end, '        global uuid\n')
        print('Inserted global uuid')
        
        with codecs.open('tests/acceptance/test_production_deployment_dr_e2e.py', 'w', encoding='utf-8') as f:
            f.writelines(lines)
        print('Added global uuid')
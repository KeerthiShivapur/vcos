with open('create_company_state.py', 'r') as f:
    content = f.read()

lines = content.split('\n')
new_lines = []
i = 0
while i < len(lines):
    line = lines[i]
    
    # Skip end_date for CompanyObjective
    if 'end_date=datetime.now(timezone.utc).date() + timedelta(days=90)' in line:
        # Check if it's in CompanyObjective context (previous lines)
        context = '\n'.join(lines[max(0,i-10):i])
        if 'CompanyObjective' in context:
            i += 1
            continue
        if 'CompanyInitiative' in context:
            i += 1
            continue
    
    if 'end_date=datetime.now(timezone.utc).date() + timedelta(days=60)' in line:
        context = '\n'.join(lines[max(0,i-10):i])
        if 'CompanyObjective' in context:
            i += 1
            continue
        if 'CompanyInitiative' in context:
            i += 1
            continue
    
    if 'target_date=datetime.now(timezone.utc).date() + timedelta(days=120)' in line:
        context = '\n'.join(lines[max(0,i-10):i])
        if 'CompanyObjective' in context:
            i += 1
            continue
    
    if 'target_date=datetime.now(timezone.utc).date() + timedelta(days=90)' in line:
        context = '\n'.join(lines[max(0,i-10):i])
        if 'CompanyInitiative' in context:
            i += 1
            continue
            
    if 'start_date=datetime.now(timezone.utc).date(),' in line:
        context = '\n'.join(lines[max(0,i-10):i])
        if 'CompanyInitiative' in context:
            i += 1
            continue
            
    new_lines.append(line)
    i += 1

content = '\n'.join(new_lines)

with open('create_company_state.py', 'w') as f:
    f.write(content)
print('Fixed date fields')
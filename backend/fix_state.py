with open('create_company_state.py', 'r') as f:
    content = f.read()

content = content.replace('state="active"', 'status="active"')

with open('create_company_state.py', 'w') as f:
    f.write(content)
print('Fixed CompanyGoal state -> status')
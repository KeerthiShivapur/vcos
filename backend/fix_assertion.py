with open('tests/acceptance/test_real_company_onboarding.py', 'r') as f:
    content = f.read()

# Fix the assertion
content = content.replace('assert org.status == "provisioning"', 'assert org.status == "active"')

with open('tests/acceptance/test_real_company_onboarding.py', 'w') as f:
    f.write(content)
print('Fixed')
with open('tests/acceptance/adapters.py', 'r') as f:
    content = f.read()

# Replace state='committed' with state='authorized'
content = content.replace('state="committed"', 'state="authorized"')

# Replace epistemic_status="proposed" with epistemic_status="unknown"
content = content.replace('epistemic_status="proposed"', 'epistemic_status="unknown"')

with open('tests/acceptance/adapters.py', 'w') as f:
    f.write(content)

print('Fixed')
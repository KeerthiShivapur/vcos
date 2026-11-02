import codecs

with codecs.open('tests/acceptance/test_production_deployment_dr_e2e.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix the multi-tenant test - remove the commit
old = '''        await db_session.commit()
        
        # Create canonical state in each org'''

new = '''        # Create canonical state in each org'''

if old in content:
    content = content.replace(old, new)
    with codecs.open('tests/acceptance/test_production_deployment_dr_e2e.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print('Fixed multi-tenant test - removed commit')
else:
    print('Pattern not found')
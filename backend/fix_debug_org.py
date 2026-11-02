import codecs

with codecs.open('tests/acceptance/test_production_deployment_dr_e2e.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Add logging for org
old_org = '''        global uuid
        org = production_company["organization"]'''

new_org = '''        global uuid
        org = production_company["organization"]
        logger.info("Test organization: id={}, name={}".format(org.id, org.name))'''

if old_org in content:
    content = content.replace(old_org, new_org)
    with codecs.open('tests/acceptance/test_production_deployment_dr_e2e.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print('Added org logging')
else:
    print('Pattern not found')
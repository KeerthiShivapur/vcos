import codecs

with codecs.open('tests/acceptance/test_production_deployment_dr_e2e.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Add print statements for debugging
old_start = '''        global uuid
        logger.info("=== Starting test_complete_production_dr_lifecycle ===")
        org = production_company["organization"]'''

new_start = '''        global uuid
        print("=== DEBUG: Starting test_complete_production_dr_lifecycle ===")
        logger.info("=== Starting test_complete_production_dr_lifecycle ===")
        org = production_company["organization"]
        print("DEBUG: org = {}".format(org))'''

if old in content:
    content = content.replace(old, new)
    with codecs.open('tests/acceptance/test_production_deployment_dr_e2e.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print('Added print statements')
else:
    print('Pattern not found')
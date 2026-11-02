import codecs

with codecs.open('tests/acceptance/test_production_deployment_dr_e2e.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Add print statements for debugging
old_start = '        global uuid\n        logger.info("=== Starting test_complete_production_dr_lifecycle ===")\n        org = production_company["organization"]'

new_start = '        global uuid\n        print("=== DEBUG: Starting test_complete_production_dr_lifecycle ===")\n        logger.info("=== Starting test_complete_production_dr_lifecycle ===")\n        org = production_company["organization"]\n        print("DEBUG: org = {}".format(org))'

if old_start in content:
    content = content.replace(old_start, new_start)
    with codecs.open('tests/acceptance/test_production_deployment_dr_e2e.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print('Added print statements')
else:
    print('Pattern not found')
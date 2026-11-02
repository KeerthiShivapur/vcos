import codecs

with codecs.open('tests/acceptance/test_production_deployment_dr_e2e.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Add print statements for backup creation
old_backup = '''        logger.info("Creating backup for org_id: {}".format(org.id))
        backup_id = "bkp-{}".format(uuid.uuid4().hex[:12])
        logger.info("Generated backup_id: {}".format(backup_id))'''

new_backup = '''        print("DEBUG: About to create backup for org_id: {}".format(org.id))
        print("DEBUG: org.id = {}".format(org.id))
        logger.info("Creating backup for org_id: {}".format(org.id))
        backup_id = "bkp-{}".format(uuid.uuid4().hex[:12])
        print("DEBUG: Generated backup_id: {}".format(backup_id))
        logger.info("Generated backup_id: {}".format(backup_id))
        print("DEBUG: backup_id variable = {}".format(backup_id))'''

if old in content:
    content = content.replace(old_backup, new_backup)
    with codecs.open('tests/acceptance/test_production_deployment_dr_e2e.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print('Added print statements for backup creation')
else:
    print('Pattern not found')
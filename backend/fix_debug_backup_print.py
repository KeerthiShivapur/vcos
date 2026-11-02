import codecs

with codecs.open('tests/acceptance/test_production_deployment_dr_e2e.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Add more print statements around backup creation and restore
old_backup_log = '''        logger.info("Creating backup for org_id: {}".format(org.id))
        backup_id = "bkp-{}".format(uuid.uuid4().hex[:12])
        logger.info("Generated backup_id: {}".format(backup_id))'''

new_backup_log = '''        print("DEBUG: About to create backup for org_id: {}".format(org.id))
        logger.info("Creating backup for org_id: {}".format(org.id))
        backup_id = "bkp-{}".format(uuid.uuid4().hex[:12])
        print("DEBUG: Generated backup_id: {}".format(backup_id))
        logger.info("Generated backup_id: {}".format(backup_id))'''

if old in content:
    content = content.replace(old_backup_log, new_backup_log)
    with codecs.open('tests/acceptance/test_production_deployment_dr_e2e.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print('Added print statements for backup creation')
else:
    print('Pattern not found')
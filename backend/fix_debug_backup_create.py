import codecs

with codecs.open('tests/acceptance/test_production_deployment_dr_e2e.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Add more detailed logging around backup creation
old_backup = '''        # Create backup manifest directly with correct organization_id
        import uuid
        import hashlib
        import uuid
        backup_id = "bkp-{}".format(uuid.uuid4().hex[:12])'''

new_backup = '''        # Create backup manifest directly with correct organization_id
        import uuid
        import hashlib
        import uuid
        logger.info("Creating backup for org_id: {}".format(org.id))
        backup_id = "bkp-{}".format(uuid.uuid4().hex[:12])
        logger.info("Generated backup_id: {}".format(backup_id))'''

if old_backup in content:
    content = content.replace(old_backup, new_backup)
    with codecs.open('tests/acceptance/test_production_deployment_dr_e2e.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print('Added debug logging for backup creation')
else:
    print('Pattern not found')
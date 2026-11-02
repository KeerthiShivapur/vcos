import codecs

with codecs.open('tests/acceptance/test_production_deployment_dr_e2e.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Add more debug logging after backup creation
old_verify = '''            logger.info("Created backup with ID: {}".format(backup_metadata.backup_id))
            logger.info("Backup organization_id: {}".format(created_backup.organization_id if created_backup else 'None'))
            if created_backup and created_backup.organization_id == org.id:
                break'''

new_verify = '''            logger.info("Created backup with ID: {}".format(backup_metadata.backup_id))
            logger.info("Backup organization_id: {}".format(created_backup.organization_id if created_backup else 'None'))
            logger.info("Expected org_id: {}".format(org.id))
            if created_backup and created_backup.organization_id == org.id:
                break'''

if old_verify in content:
    content = content.replace(old_verify, new_verify)
    with codecs.open('tests/acceptance/test_production_deployment_dr_e2e.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print('Added more debug logging')
else:
    print('Block not found')
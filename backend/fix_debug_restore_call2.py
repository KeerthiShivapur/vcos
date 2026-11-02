import codecs

with codecs.open('tests/acceptance/test_production_deployment_dr_e2e.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Add debug logging before restore call
old_restore_call = '''        logger.info("Restore backup org_id: {}".format(restore_backup.organization_id if restore_backup else 'None'))
        logger.info("Expected org_id: {}".format(org.id))
        
        restore_result = await restore_service.restore_from_backup('''

new_restore_call = '''        logger.info("Restore backup org_id: {}".format(restore_backup.organization_id if restore_backup else 'None'))
        logger.info("Expected org_id: {}".format(org.id))
        
        print("DEBUG: Calling restore with backup_id={}".format(backup_id))
        print("DEBUG: org.id for restore = {}".format(org.id))
        
        restore_result = await restore_service.restore_from_backup('''

if old_restore_call in content:
    content = content.replace(old_restore_call, new_restore_call)
    with codecs.open('tests/acceptance/test_production_deployment_dr_e2e.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print('Added debug logging before restore call')
else:
    print('Pattern not found')
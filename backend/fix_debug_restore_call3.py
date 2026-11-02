import codecs

with codecs.open('tests/acceptance/test_production_deployment_dr_e2e.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Add debug logging right before restore call
old_restore_call = '''        print("DEBUG: Calling restore with backup_id={}".format(backup_id))
        print("DEBUG: org.id for restore = {}".format(org.id))
        
        restore_result = await restore_service.restore_from_backup('''

new_restore_call = '''        print("DEBUG: About to call restore, backup_id = {}".format(backup_id))
        print("DEBUG: org.id = {}".format(org.id))
        # Verify backup exists in DB with correct org_id
        from sqlalchemy import select
        check = await db_session.execute(select(BackupManifest.organization_id).where(BackupManifest.id == backup_id))
        check_org_id = check.scalar()
        print("DEBUG: Backup in DB org_id: {}".format(check_org_id))
        print("DEBUG: Match: {}".format(check_org_id == org.id))
        
        restore_result = await restore_service.restore_from_backup('''

if old_restore_call in content:
    content = content.replace(old_restore_call, new_restore_call)
    with codecs.open('tests/acceptance/test_production_deployment_dr_e2e.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print('Added debug logging before restore call')
else:
    print('Pattern not found')
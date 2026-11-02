import codecs

with codecs.open('tests/acceptance/test_production_deployment_dr_e2e.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Add debug logging after flush to check organization_id in DB
old_flush = '''        db_session.add(backup_metadata)
        await db_session.flush()
        
        # Create a simple metadata object for compatibility'''

new_flush = '''        db_session.add(backup_metadata)
        await db_session.flush()
        print("DEBUG: BackupManifest flushed, checking organization_id in DB...")
        from sqlalchemy import select
        check = await db_session.execute(select(BackupManifest.organization_id).where(BackupManifest.id == backup_id))
        check_org_id = check.scalar()
        print("DEBUG: BackupManifest organization_id in DB after flush: {}".format(check_org_id))
        print("DEBUG: Expected org.id: {}".format(org.id))
        print("DEBUG: Match: {}".format(check_org_id == org.id))
        
        # Create a simple metadata object for compatibility'''

if old_flush in content:
    content = content.replace(old_flush, new_flush)
    with codecs.open('tests/acceptance/test_production_deployment_dr_e2e.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print('Added debug logging after flush')
else:
    print('Pattern not found')
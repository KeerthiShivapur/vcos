import codecs

with codecs.open('tests/acceptance/test_production_deployment_dr_e2e.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Remove the local import of select
old_flush = '''        print("DEBUG: BackupManifest flushed, checking organization_id in DB...")
        from sqlalchemy import select
        check = await db_session.execute(select(BackupManifest.organization_id).where(BackupManifest.id == backup_id))'''

new_flush = '''        print("DEBUG: BackupManifest flushed, checking organization_id in DB...")
        check = await db_session.execute(select(BackupManifest.organization_id).where(BackupManifest.id == backup_id))'''

if old_flush in content:
    content = content.replace(old_flush, new_flush)
    with codecs.open('tests/acceptance/test_production_deployment_dr_e2e.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print('Removed local import of select')
else:
    print('Pattern not found')
import codecs

with codecs.open('tests/acceptance/test_production_deployment_dr_e2e.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Remove the local import of select
old_check = '''        # Verify backup exists in DB with correct org_id
        from sqlalchemy import select
        check = await db_session.execute(select(BackupManifest.organization_id).where(BackupManifest.id == backup_id))'''

new_check = '''        # Verify backup exists in DB with correct org_id
        check = await db_session.execute(select(BackupManifest.organization_id).where(BackupManifest.id == backup_id))'''

if old_check in content:
    content = content.replace(old_check, new_check)
    with codecs.open('tests/acceptance/test_production_deployment_dr_e2e.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print('Removed local import of select')
else:
    print('Pattern not found')
import codecs

with codecs.open('tests/acceptance/test_production_deployment_dr_e2e.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Add commit after cleanup to ensure old data is removed
old_cleanup = '''        # Aggressive cleanup - delete ALL backups to avoid conflicts from previous test runs
        from app.models.backup_manifest import BackupManifest
        from sqlalchemy import delete
        await db_session.execute(delete(BackupManifest))
        await db_session.flush()'''

new_cleanup = '''        # Aggressive cleanup - delete ALL backups to avoid conflicts from previous test runs
        from app.models.backup_manifest import BackupManifest
        from sqlalchemy import delete
        await db_session.execute(delete(BackupManifest))
        await db_session.flush()
        await db_session.commit()  # Ensure cleanup is committed'''

if old_cleanup in content:
    content = content.replace(old_cleanup, new_cleanup)
    with codecs.open('tests/acceptance/test_production_deployment_dr_e2e.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print('Added commit after cleanup')
else:
    print('Cleanup section not found')
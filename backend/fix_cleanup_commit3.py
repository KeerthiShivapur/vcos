import codecs

with codecs.open('tests/acceptance/test_production_deployment_dr_e2e.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Add commit after cleanup
old = '''        # Clean up any existing backups
        from sqlalchemy import delete
        await db_session.execute(delete(BackupManifest))
        await db_session.flush()
        
        # Create backup manifest directly with correct organization_id'''

new = '''        # Clean up any existing backups
        from sqlalchemy import delete
        await db_session.execute(delete(BackupManifest))
        await db_session.flush()
        await db_session.commit()  # Ensure cleanup is committed
        
        # Create backup manifest directly with correct organization_id'''

if old in content:
    content = content.replace(old, new)
    with codecs.open('tests/acceptance/test_production_deployment_dr_e2e.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print('Added commit after cleanup')
else:
    print('Pattern not found')
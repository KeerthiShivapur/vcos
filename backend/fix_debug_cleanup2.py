import codecs

with codecs.open('tests/acceptance/test_production_deployment_dr_e2e.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Add more debug logging
old = '''        # Clean up any existing backups
        from sqlalchemy import delete
        await db_session.execute(delete(BackupManifest))
        await db_session.flush()
        await db_session.commit()  # Ensure cleanup is committed
        logger.info("Cleanup committed, deleted old backups")
        
        # Create backup manifest directly with correct organization_id'''

new = '''        # Clean up any existing backups
        from sqlalchemy import delete
        logger.info("Starting cleanup of BackupManifest table")
        result = await db_session.execute(delete(BackupManifest))
        logger.info("Delete executed, rowcount: {}".format(result.rowcount))
        await db_session.flush()
        await db_session.commit()  # Ensure cleanup is committed
        logger.info("Cleanup committed, deleted old backups")
        
        # Verify cleanup worked
        remaining = await db_session.execute(select(func.count()).select_from(BackupManifest))
        count = remaining.scalar()
        logger.info("Backups remaining after cleanup: {}".format(count))
        
        # Create backup manifest directly with correct organization_id'''

if old in content:
    content = content.replace(old, new)
    with codecs.open('tests/acceptance/test_production_deployment_dr_e2e.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print('Added more debug logging')
else:
    print('Pattern not found')
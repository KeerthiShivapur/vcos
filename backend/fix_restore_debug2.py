import codecs

with codecs.open('tests/acceptance/test_production_deployment_dr_e2e.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Add debug logging for restore
old_restore = '''        restore_result = await restore_service.restore_from_backup(
            db=db_session,
            backup_id=backup_id,
            organization_id=org.id,
            initiated_by="dr_test",
            target_time=None,  # Full restore to backup point
        )'''

new_restore = '''        logger.info("Restoring with backup_id: {}".format(backup_id))
        # Verify backup belongs to our organization
        from app.models.backup_manifest import BackupManifest
        restore_backup = await db_session.get(BackupManifest, backup_id)
        logger.info("Restore backup org_id: {}".format(restore_backup.organization_id if restore_backup else 'None'))
        logger.info("Expected org_id: {}".format(org.id))
        
        restore_result = await restore_service.restore_from_backup(
            db=db_session,
            backup_id=backup_id,
            organization_id=org.id,
            initiated_by="dr_test",
            target_time=None,  # Full restore to backup point
        )'''

if old_restore in content:
    content = content.replace(old_restore, new_restore)
    with codecs.open('tests/acceptance/test_production_deployment_dr_e2e.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print('Added debug logging for restore')
else:
    print('Block not found')
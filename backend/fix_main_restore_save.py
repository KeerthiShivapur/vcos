import codecs

with codecs.open('tests/acceptance/test_production_deployment_dr_e2e.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Save the main restore result before adversarial tests
old_restore = '''        restore_result = await restore_service.restore_from_backup(
            db=db_session,
            backup_id=backup_id,
            organization_id=org.id,
            initiated_by="dr_test",
            target_time=None,  # Full restore to backup point
        )
        
        assert restore_result["success"], f"Restore failed: {restore_result}"
        restore_id = restore_result["restore_id"]
        
        measurement_service.record_phase(RecoveryPhase.RESTORE_COMPLETED)'''

new_restore = '''        main_restore_result = await restore_service.restore_from_backup(
            db=db_session,
            backup_id=backup_id,
            organization_id=org.id,
            initiated_by="dr_test",
            target_time=None,  # Full restore to backup point
        )
        
        assert main_restore_result["success"], f"Restore failed: {main_restore_result}"
        restore_id = main_restore_result["restore_id"]
        main_restore_mock = main_restore_result.get("mock", False)
        
        measurement_service.record_phase(RecoveryPhase.RESTORE_COMPLETED)'''

if old_restore in content:
    content = content.replace(old_restore, new_restore)
    with codecs.open('tests/acceptance/test_production_deployment_dr_e2e.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print('Saved main restore result')
else:
    print('Pattern not found')
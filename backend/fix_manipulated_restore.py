import codecs

with codecs.open('app/services/restore_service.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix the manipulated manifest test call to restore_from_backup
old_manipulated_restore = '''            # Attempt restore - should fail due to checksum validation
            restore_result = await self.restore_from_backup(
                db=db,
                backup_id=bad_backup.id,
                organization_id=organization_id,
                initiated_by="adversarial_test",
            )'''

new_manipulated_restore = '''            # Attempt restore - should fail due to checksum validation
            restore_result = await self.restore_from_backup(
                db=db,
                backup_id=bad_backup.id,
                organization_id=organization_id,
                initiated_by="adversarial_test",
                skip_recording=True,
            )'''

if old_manipulated_restore in content:
    content = content.replace(old_manipulated_restore, new_manipulated_restore)
    print('Fixed manipulated manifest restore call')
else:
    print('Manipulated manifest restore pattern not found')

with codecs.open('app/services/restore_service.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Done')
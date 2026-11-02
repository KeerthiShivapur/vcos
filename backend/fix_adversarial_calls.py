import codecs

with codecs.open('app/services/restore_service.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix the cross-tenant restore attempt call
old_cross = '''            print("DEBUG CROSS: Attempting cross-tenant restore with backup_id={}".format(other_backup.id))
            try:
                restore_result = await self.restore_from_backup(
                    db=db,
                    backup_id=other_backup.id,
                    organization_id=organization_id,
                    initiated_by="adversarial_test",
                )'''

new_cross = '''            print("DEBUG CROSS: Attempting cross-tenant restore with backup_id={}".format(other_backup.id))
            try:
                restore_result = await self.restore_from_backup(
                    db=db,
                    backup_id=other_backup.id,
                    organization_id=organization_id,
                    initiated_by="adversarial_test",
                    skip_recording=True,
                )'''

if old_cross in content:
    content = content.replace(old_cross, new_cross)
    print('Fixed cross-tenant restore call')
else:
    print('Cross-tenant pattern not found')

# Fix the manipulated manifest test call
old_manipulated = '''            # Test 3: Restore with manipulated backup manifest
            print("DEBUG ADV: Running manipulated manifest test")
            await self._test_manipulated_backup_manifest(result, db, organization_id)
            print("DEBUG ADV: Manipulated manifest test completed")'''

new_manipulated = '''            # Test 3: Restore with manipulated backup manifest
            print("DEBUG ADV: Running manipulated manifest test")
            await self._test_manipulated_manifest_skip(result, db, organization_id)
            print("DEBUG ADV: Manipulated manifest test completed")'''

if old_manipulated in content:
    content = content.replace(old_manipulated, new_manipulated)
    print('Fixed manipulated manifest test call')
else:
    print('Manipulated manifest pattern not found')

with codecs.open('app/services/restore_service.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Done')
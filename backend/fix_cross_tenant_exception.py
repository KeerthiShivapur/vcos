import codecs

with codecs.open('app/services/restore_service.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix the duplicate except block and restore_result reference
old_cross = '''            print("DEBUG CROSS: Caught exception: {}".format(e))
                # Expected - restore should fail
                result.add_check(ValidationCheck(
                    name="cross_tenant_restore_attempt",
                    status=ValidationStatus.VERIFIED,
                    message="Cross-tenant restore correctly rejected",
                    details={"error": str(e)},
                ))
                
                # Restore should fail due to tenant isolation
                if restore_result.get("success", False):
                    result.add_check(ValidationCheck(
                        name="cross_tenant_restore_attempt",
                        status=ValidationStatus.FAILED,
                        message="Cross-tenant restore unexpectedly succeeded",
                        details={"other_backup_id": other_backup.id},
                    ))
                else:
                    result.add_check(ValidationCheck(
                        name="cross_tenant_restore_attempt",
                        status=ValidationStatus.VERIFIED,
                        message="Cross-tenant restore correctly rejected",
                        details={"other_backup_id": other_backup.id},
                    ))
            except Exception as e:
                # Expected - restore should fail
                result.add_check(ValidationCheck(
                    name="cross_tenant_restore_attempt",
                    status=ValidationStatus.VERIFIED,
                    message="Cross-tenant restore correctly rejected",
                    details={"error": str(e)},
                ))'''

new_cross = '''            print("DEBUG CROSS: Caught exception: {}".format(e))
                # Expected - restore should fail
                result.add_check(ValidationCheck(
                    name="cross_tenant_restore_attempt",
                    status=ValidationStatus.VERIFIED,
                    message="Cross-tenant restore correctly rejected",
                    details={"error": str(e)},
                ))'''

if old_cross in content:
    content = content.replace(old_cross, new_cross)
    with codecs.open('app/services/restore_service.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print('Fixed cross-tenant test exception handling')
else:
    print('Pattern not found')
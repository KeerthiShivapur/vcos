import codecs

with codecs.open('app/services/restore_service.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Add debug logging to _run_restore_specific_adversarial_tests
old_run = '''    async def _run_restore_specific_adversarial_tests(
        self,
        result: ValidationResult,
        db: AsyncSession,
        organization_id: str,
    ) -> None:
        """Run restore-specific adversarial tests for tenant isolation."""
        try:
            # Test 1: Cross-tenant restore attempt
            await self._test_cross_tenant_restore_attempt(result, db, organization_id)
            
            # Test 2: Restore with mixed tenant data in backup
            await self._test_restore_mixed_tenant_data(result, db, organization_id)
            
            # Test 3: Restore with manipulated backup manifest
            await self._test_manipulated_backup_manifest(result, db, organization_id)
            
            # Test 4: Cross-tenant backup access
            await self._test_cross_tenant_backup_access(result, db, organization_id)
            
            result.add_check(ValidationCheck(
                name="restore_adversarial_tests",
                status=ValidationStatus.VERIFIED,
                message="All restore-specific adversarial tests passed",
                details={"tests_run": 4},
            ))
        except Exception as e:
            result.add_check(ValidationCheck(
                name="restore_adversarial_tests",
                status=ValidationStatus.INCONCLUSIVE,
                message=f"Restore adversarial tests failed: {str(e)}",
                details={"error": str(e)},
            ))'''

new_run = '''    async def _run_restore_specific_adversarial_tests(
        self,
        result: ValidationResult,
        db: AsyncSession,
        organization_id: str,
    ) -> None:
        """Run restore-specific adversarial tests for tenant isolation."""
        print("DEBUG ADV: Starting restore-specific adversarial tests")
        try:
            # Test 1: Cross-tenant restore attempt
            print("DEBUG ADV: Running cross-tenant restore attempt")
            await self._test_cross_tenant_restore_attempt(result, db, organization_id)
            print("DEBUG ADV: Cross-tenant test completed")
            
            # Test 2: Restore with mixed tenant data in backup
            print("DEBUG ADV: Running mixed tenant data test")
            await self._test_restore_mixed_tenant_data(result, db, organization_id)
            print("DEBUG ADV: Mixed tenant test completed")
            
            # Test 3: Restore with manipulated backup manifest
            print("DEBUG ADV: Running manipulated manifest test")
            await self._test_manipulated_backup_manifest(result, db, organization_id)
            print("DEBUG ADV: Manipulated manifest test completed")
            
            # Test 4: Cross-tenant backup access
            print("DEBUG ADV: Running cross-tenant backup access test")
            await self._test_cross_tenant_backup_access(result, db, organization_id)
            print("DEBUG ADV: Cross-tenant backup access test completed")
            
            result.add_check(ValidationCheck(
                name="restore_adversarial_tests",
                status=ValidationStatus.VERIFIED,
                message="All restore-specific adversarial tests passed",
                details={"tests_run": 4},
            ))
            print("DEBUG ADV: All adversarial tests passed")
        except Exception as e:
            print("DEBUG ADV: Caught exception in adversarial tests: {}".format(e))
            result.add_check(ValidationCheck(
                name="restore_adversarial_tests",
                status=ValidationStatus.INCONCLUSIVE,
                message=f"Restore adversarial tests failed: {str(e)}",
                details={"error": str(e)},
            ))'''

if old_run in content:
    content = content.replace(old_run, new_run)
    with codecs.open('app/services/restore_service.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print('Added debug logging to adversarial tests')
else:
    print('Pattern not found')
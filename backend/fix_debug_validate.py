import codecs

with codecs.open('app/services/restore_service.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Add debug logging to _validate_tenant_isolation
old_validate = '''    async def _validate_tenant_isolation(self, db: AsyncSession, organization_id: str) -> ValidationResult:
        """Validate tenant isolation after restore using adversarial tests.""""
        self.detector.db = db
        result = ValidationResult(domain="tenant_isolation")
        
        # Run standard adversarial tests
        try:
            from tests.acceptance.test_tenant_isolation_adversarial import (
                TenantIsolationAdversarialTests,
            )
            
            # Create test callers
            caller_a = await self._create_test_caller(db, organization_id, "test-a")
            caller_b = await self._create_test_caller(db, organization_id, "test-b")
            
            tester = TenantIsolationAdversarialTests(db, caller_a, caller_b)
            test_result = await tester.run_all_tests()
            
            if test_result["failed"] == 0:
                result.add_check(ValidationCheck(
                    name="adversarial_tests",
                    status=ValidationStatus.VERIFIED,
                    message=f"All {test_result['passed']}/{test_result['total_tests']} adversarial tests passed",
                    details=test_result,
                ))
            else:
                result.add_check(ValidationCheck(
                    name="adversarial_tests",
                    status=ValidationStatus.FAILED,
                    message=f"{test_result['failed']}/{test_result['total_tests']} adversarial tests failed",
                    details=test_result,
                ))
        except Exception as e:
            result.add_check(ValidationCheck(
                name="adversarial_tests",
                status=ValidationStatus.INCONCLUSIVE,
                message=f"Tenant isolation test failed to run: {str(e)}",
                details={"error": str(e)},
            ))
        
        # Run restore-specific adversarial tests
        await self._run_restore_specific_adversarial_tests(result, db, organization_id)
        
        result.determine_overall()
        return result'''

new_validate = '''    async def _validate_tenant_isolation(self, db: AsyncSession, organization_id: str) -> ValidationResult:
        """Validate tenant isolation after restore using adversarial tests."""
        print("DEBUG VALIDATE: Starting tenant isolation validation")
        self.detector.db = db
        result = ValidationResult(domain="tenant_isolation")
        
        # Run standard adversarial tests
        print("DEBUG VALIDATE: Running standard adversarial tests")
        try:
            from tests.acceptance.test_tenant_isolation_adversarial import (
                TenantIsolationAdversarialTests,
            )
            
            # Create test callers
            caller_a = await self._create_test_caller(db, organization_id, "test-a")
            caller_b = await self._create_test_caller(db, organization_id, "test-b")
            
            tester = TenantIsolationAdversarialTests(db, caller_a, caller_b)
            test_result = await tester.run_all_tests()
            print("DEBUG VALIDATE: Standard adversarial tests result: {}".format(test_result))
            
            if test_result["failed"] == 0:
                result.add_check(ValidationCheck(
                    name="adversarial_tests",
                    status=ValidationStatus.VERIFIED,
                    message=f"All {test_result['passed']}/{test_result['total_tests']} adversarial tests passed",
                    details=test_result,
                ))
            else:
                result.add_check(ValidationCheck(
                    name="adversarial_tests",
                    status=ValidationStatus.FAILED,
                    message=f"{test_result['failed']}/{test_result['total_tests']} adversarial tests failed",
                    details=test_result,
                ))
        except Exception as e:
            print("DEBUG VALIDATE: Standard adversarial tests failed with exception: {}".format(e))
            result.add_check(ValidationCheck(
                name="adversarial_tests",
                status=ValidationStatus.INCONCLUSIVE,
                message=f"Tenant isolation test failed to run: {str(e)}",
                details={"error": str(e)},
            ))
        
        # Run restore-specific adversarial tests
        print("DEBUG VALIDATE: Running restore-specific adversarial tests")
        await self._run_restore_specific_adversarial_tests(result, db, organization_id)
        print("DEBUG VALIDATE: Restore-specific adversarial tests completed")
        
        result.determine_overall()
        print("DEBUG VALIDATE: Validation result overall status: {}".format(result.overall_status))
        return result'''

if old_validate in content:
    content = content.replace(old_validate, new_validate)
    with codecs.open('app/services/restore_service.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print('Added debug logging to tenant isolation validation')
else:
    print('Pattern not found')
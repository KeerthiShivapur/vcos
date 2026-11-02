import codecs

with codecs.open('app/services/restore_service.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Add debug logging to _phase_tenant_isolation_validated
old_phase = '''    async def _phase_tenant_isolation_validated(self, db: AsyncSession, context: RestoreContext, restore_op: RestoreOperation) -> Dict[str, Any]:
        """Phase 7: Validate tenant isolation after restore."""
        try:
            validation = await self._validate_tenant_isolation(db, context.organization_id)
            context.validation_results["tenant_isolation"] = validation
            
            if validation.overall_status == ValidationStatus.FAILED:
                return {"passed": False, "message": f"Tenant isolation validation failed: {validation.message}", "details": validation.to_dict(), "validation_status": ValidationStatus.FAILED.value, "validation_details": validation}
            
            return {"passed": True, "message": "Tenant isolation validated", "details": validation.to_dict(), "validation_status": validation.overall_status.value, "validation_details": validation}
        except Exception as e:
            return {"passed": False, "message": f"Tenant isolation validation failed: {str(e)}", "validation_status": ValidationStatus.FAILED.value}'''

new_phase = '''    async def _phase_tenant_isolation_validated(self, db: AsyncSession, context: RestoreContext, restore_op: RestoreOperation) -> Dict[str, Any]:
        """Phase 7: Validate tenant isolation after restore."""
        print("DEBUG PHASE: _phase_tenant_isolation_validated started")
        try:
            validation = await self._validate_tenant_isolation(db, context.organization_id)
            context.validation_results["tenant_isolation"] = validation
            print("DEBUG PHASE: Validation completed, overall_status={}".format(validation.overall_status))
            
            if validation.overall_status == ValidationStatus.FAILED:
                print("DEBUG PHASE: Validation FAILED, returning failed")
                return {"passed": False, "message": f"Tenant isolation validation failed: {validation.message}", "details": validation.to_dict(), "validation_status": ValidationStatus.FAILED.value, "validation_details": validation}
            
            print("DEBUG PHASE: Validation VERIFIED, returning passed")
            return {"passed": True, "message": "Tenant isolation validated", "details": validation.to_dict(), "validation_status": validation.overall_status.value, "validation_details": validation}
        except Exception as e:
            print("DEBUG PHASE: Exception in _phase_tenant_isolation_validated: {}".format(e))
            import traceback
            traceback.print_exc()
            return {"passed": False, "message": f"Tenant isolation validation failed: {str(e)}", "validation_status": ValidationStatus.FAILED.value}'''

if old_phase in content:
    content = content.replace(old_phase, new_phase)
    with codecs.open('app/services/restore_service.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print('Added debug logging to _phase_tenant_isolation_validated')
else:
    print('Pattern not found')
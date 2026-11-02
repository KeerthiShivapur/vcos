import codecs

with codecs.open('app/services/restore_service.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix _phase_recovery_approved to exclude itself from the check
old_recovery = '''    async def _phase_recovery_approved(self, db: AsyncSession, context: RestoreContext, restore_op: RestoreOperation) -> Dict[str, Any]:
        """Phase 14: Recovery approved for activation."""
        print("DEBUG RECOVERY: _phase_recovery_approved started")
        print("DEBUG RECOVERY: Total phases in context: {}".format(len(context.phases)))
        for pr in context.phases:
            print("DEBUG RECOVERY: Phase record: phase={}, passed={}, message={}".format(pr.get('phase'), pr.get('passed'), pr.get('message')))
        
        # Final comprehensive validation - check all previous phases in the main PHASE_ORDER
        all_passed = True
        messages = []
        
        for phase_record in context.phases:
            # Only check phases that are in the main PHASE_ORDER (not adversarial test phases)
            if phase_record.get("phase") in PHASE_ORDER:
                passed = phase_record.get("passed", False)
                print("DEBUG RECOVERY: Checking phase {}: passed={}, message={}".format(phase_record.get('phase'), phase_record.get('passed'), phase_record.get('message')))
                if not phase_record.get("passed", False):
                    all_passed = False
                    messages.append(f"{phase_record['phase']}: {phase_record.get('message', 'Failed')}")
        
        if not all_passed:
            print("DEBUG RECOVERY: FAILED - messages: {}".format(messages))
            return {"passed": False, "message": "Not all phases passed: " + "; ".join(messages), "validation_status": ValidationStatus.FAILED.value}
        
        # Additional check: no phase should be BLOCKED or INCONCLUSIVE for critical domains
        critical_domains = ["schema", "canonical_integrity", "tenant_isolation", "temporal", "provenance", "epistemic", "governance"]
        for domain in critical_domains:
            if domain in context.validation_results:
                vr = context.validation_results[domain]
                if vr.overall_status in (ValidationStatus.BLOCKED, ValidationStatus.INCONCLUSIVE):
                    return {"passed": False, "message": f"Critical domain {domain} is {vr.overall_status.value}", "validation_status": ValidationStatus.BLOCKED.value}
        
        print("DEBUG RECOVERY: All checks passed, returning VERIFIED")
        return {"passed": True, "message": "Recovery approved for activation", "validation_status": ValidationStatus.VERIFIED.value}'''

new_recovery = '''    async def _phase_recovery_approved(self, db: AsyncSession, context: RestoreContext, restore_op: RestoreOperation) -> Dict[str, Any]:
        """Phase 14: Recovery approved for activation."""
        print("DEBUG RECOVERY: _phase_recovery_approved started")
        print("DEBUG RECOVERY: Total phases in context: {}".format(len(context.phases)))
        for pr in context.phases:
            print("DEBUG RECOVERY: Phase record: phase={}, passed={}, message={}".format(pr.get('phase'), pr.get('passed'), pr.get('message')))
        
        # Final comprehensive validation - check all previous phases in the main PHASE_ORDER
        # Exclude RECOVERY_APPROVED itself from the check to avoid circular dependency
        all_passed = True
        messages = []
        
        for phase_record in context.phases:
            # Only check phases that are in the main PHASE_ORDER (not adversarial test phases)
            # Exclude RECOVERY_APPROVED itself to avoid circular dependency
            phase_name = phase_record.get("phase")
            if phase_name in PHASE_ORDER and phase_name != "RECOVERY_APPROVED":
                passed = phase_record.get("passed", False)
                print("DEBUG RECOVERY: Checking phase {}: passed={}, message={}".format(phase_record.get('phase'), phase_record.get('passed'), phase_record.get('message')))
                if not phase_record.get("passed", False):
                    all_passed = False
                    messages.append(f"{phase_record['phase']}: {phase_record.get('message', 'Failed')}")
        
        if not all_passed:
            print("DEBUG RECOVERY: FAILED - messages: {}".format(messages))
            return {"passed": False, "message": "Not all phases passed: " + "; ".join(messages), "validation_status": ValidationStatus.FAILED.value}
        
        # Additional check: no phase should be BLOCKED or INCONCLUSIVE for critical domains
        critical_domains = ["schema", "canonical_integrity", "tenant_isolation", "temporal", "provenance", "epistemic", "governance"]
        for domain in critical_domains:
            if domain in context.validation_results:
                vr = context.validation_results[domain]
                if vr.overall_status in (ValidationStatus.BLOCKED, ValidationStatus.INCONCLUSIVE):
                    return {"passed": False, "message": f"Critical domain {domain} is {vr.overall_status.value}", "validation_status": ValidationStatus.BLOCKED.value}
        
        print("DEBUG RECOVERY: All checks passed, returning VERIFIED")
        return {"passed": True, "message": "Recovery approved for activation", "validation_status": ValidationStatus.VERIFIED.value}'''

if old_recovery in content:
    content = content.replace(old_recovery, new_recovery)
    with codecs.open('app/services/restore_service.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print('Fixed _phase_recovery_approved to exclude self-check')
else:
    print('Pattern not found')
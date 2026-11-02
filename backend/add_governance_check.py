with open('app/intelligence/canonical_mutation.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Replace the governance check section with actual enforcement
old_governance = '''    # ================================================================
    # 7. GOVERNANCE AUTHORIZATION FOR EPISTEMIC PROMOTION
    # ================================================================
    # Governance authorization is already enforced by validate_governance
    # which is called before validate_epistemic_integrity in the mutation wrapper.
    # No additional governance checks needed here.
    pass'''

new_governance = '''    # ================================================================
    # 7. GOVERNANCE AUTHORIZATION FOR EPISTEMIC PROMOTION
    # ================================================================
    # Strong epistemic promotions require appropriate governance permissions.
    # This check applies to all mutation types including CREATE.
    promotion_requiring_governance = {
        EpistemicStatus.EVIDENCE_BACKED: ["decisions:manage", "evidence:validate"],
        EpistemicStatus.MEASURED: ["decisions:manage", "evidence:validate"],
        EpistemicStatus.OBSERVED: ["decisions:manage", "evidence:validate", "governance:approve"],
    }
    
    required_perms = promotion_requiring_governance.get(context.epistemic_status, [])
    if required_perms:
        caller_perms = await context.caller.get_permissions(db) if db else frozenset()
        for perm in required_perms:
            if perm not in caller_perms:
                raise EpistemicPromotionViolation(
                    f"Promotion to {context.epistemic_status} requires permission: {perm}"
                )'''

content = content.replace(old_governance, new_governance)

with open('app/intelligence/canonical_mutation.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Added governance check to validate_epistemic_integrity')
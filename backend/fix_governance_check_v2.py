with open('app/intelligence/canonical_mutation.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Update the governance check to use decisions:manage instead of evidence:validate
old_governance = '''    # ================================================================
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

new_governance = '''    # ================================================================
    # 7. GOVERNANCE AUTHORIZATION FOR EPISTEMIC PROMOTION
    # ================================================================
    # Strong epistemic promotions require appropriate governance permissions.
    # This check applies to all mutation types including CREATE.
    promotion_requiring_governance = {
        EpistemicStatus.EVIDENCE_BACKED: ["decisions:manage"],
        EpistemicStatus.MEASURED: ["decisions:manage"],
        EpistemicStatus.OBSERVED: ["decisions:manage", "governance:approve"],
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

print('Updated governance check to use decisions:manage')